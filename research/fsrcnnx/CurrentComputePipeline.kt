package com.example.liteplayer
import android.content.Context
import android.opengl.GLES11Ext
import android.opengl.GLES30 as GL
import android.opengl.GLES31 as C

internal class CurrentComputePipeline(context:Context,model:String) {
    private data class Stage(val scale:Int,val tw:Int,val th:Int,val name:String,val inputs:List<String>,val program:Int)
    private data class Tex(val id:Int,val w:Int,val h:Int)
    private val stages=ArrayList<Stage>()
    private val targets=ArrayList<Tex>()
    private var luma:Tex?=null
    private var fbo=0
    private var vao=0
    private var extract=0
    private var composite=0
    private var valid=false
    private val lastMatrix=FloatArray(16)
    private var lastVideo=0
    private val vertex="""#version 300 es
precision highp float;
out vec2 uv;
void main(){
vec2 p=vec2(float((gl_VertexID&1)*2-1),float(((gl_VertexID>>1)&1)*2-1));
uv=p*0.5+0.5; gl_Position=vec4(p,0.0,1.0);
}"""
    init {
        try {
            val ver=IntArray(1)
            GL.glGetIntegerv(GL.GL_MINOR_VERSION,ver,0)
            val minor=ver[0]
            GL.glGetIntegerv(GL.GL_MAJOR_VERSION,ver,0)
            check(ver[0]>3 || (ver[0]==3 && minor>=1)){"OpenGL ES 3.1 required"}
            fun read(file:String)=context.assets.open("reflite/"+file).bufferedReader().use{it.readText()}
            read(model+".stages").lineSequence().filter{it.isNotBlank()}.forEachIndexed{i,line->
                val p=line.split(',')
                stages.add(Stage(p[0].toInt(),p[1].toInt(),p[2].toInt(),p[3],p.drop(4),
                    link(C.GL_COMPUTE_SHADER to read(model+"-"+i+".comp"))))
            }
            check(stages.size==if(model=="ArtCNN") 8 else 6)
            val id=IntArray(1)
            GL.glGenFramebuffers(1,id,0);fbo=id[0]
            GL.glGenVertexArrays(1,id,0);vao=id[0]
            extract=link(GL.GL_VERTEX_SHADER to vertex,GL.GL_FRAGMENT_SHADER to """#version 300 es
#extension GL_OES_EGL_image_external_essl3 : require
precision highp float;
uniform samplerExternalOES video;uniform mat4 matrix;
in vec2 uv;out vec4 color;
void main(){
vec3 rgb=texture(video,(matrix*vec4(uv,0.,1.)).xy).rgb;
color=vec4(dot(rgb,vec3(.2126,.7152,.0722)),0.,0.,1.);
}""")
            composite=link(GL.GL_VERTEX_SHADER to vertex,GL.GL_FRAGMENT_SHADER to """#version 300 es
#extension GL_OES_EGL_image_external_essl3 : require
precision highp float;
uniform samplerExternalOES video;uniform mat4 matrix;uniform sampler2D learned;
in vec2 uv;out vec4 color;
void main(){
vec3 rgb=texture(video,(matrix*vec4(uv,0.,1.)).xy).rgb;
float orig=dot(rgb,vec3(.2126,.7152,.0722));
float y=texture(learned,uv).r;
color=vec4(clamp(rgb+vec3(y-orig),0.,1.),1.);
}""")
        } catch(t:Throwable){close();throw t}
    }
    private fun link(vararg sources:Pair<Int,String>):Int {
        val p=GL.glCreateProgram()
        val ids=ArrayList<Int>()
        try {
            for((type,src) in sources){
                val id=GL.glCreateShader(type);ids.add(id)
                GL.glShaderSource(id,src);GL.glCompileShader(id)
                val ok=IntArray(1);GL.glGetShaderiv(id,GL.GL_COMPILE_STATUS,ok,0)
                check(ok[0]==GL.GL_TRUE){GL.glGetShaderInfoLog(id)}
                GL.glAttachShader(p,id)
            }
            GL.glLinkProgram(p)
            val ok=IntArray(1);GL.glGetProgramiv(p,GL.GL_LINK_STATUS,ok,0)
            check(ok[0]==GL.GL_TRUE){GL.glGetProgramInfoLog(p)}
            return p
        }catch(t:Throwable){GL.glDeleteProgram(p);throw t}
        finally {ids.forEach{GL.glDeleteShader(it)}}
    }
    private fun allocate(w:Int,h:Int):Tex {
        val id=IntArray(1);GL.glGenTextures(1,id,0)
        GL.glBindTexture(GL.GL_TEXTURE_2D,id[0])
        GL.glTexStorage2D(GL.GL_TEXTURE_2D,1,GL.GL_RGBA16F,w,h)
        for(p in intArrayOf(GL.GL_TEXTURE_MIN_FILTER,GL.GL_TEXTURE_MAG_FILTER))
            GL.glTexParameteri(GL.GL_TEXTURE_2D,p,GL.GL_LINEAR)
        for(p in intArrayOf(GL.GL_TEXTURE_WRAP_S,GL.GL_TEXTURE_WRAP_T))
            GL.glTexParameteri(GL.GL_TEXTURE_2D,p,GL.GL_CLAMP_TO_EDGE)
        return Tex(id[0],w,h)
    }
    private fun release(){
        (targets+listOfNotNull(luma)).distinctBy{it.id}.forEach{GL.glDeleteTextures(1,intArrayOf(it.id),0)}
        targets.clear();luma=null;valid=false
    }
    private fun ensure(w:Int,h:Int){
        if(luma?.w==w && luma?.h==h)return
        release()
        luma=allocate(w,h)
        val last=IntArray(stages.size){it}
        val names=HashMap<String,Int>()
        stages.forEachIndexed{i,s->
            s.inputs.filter{it!="LUMA"}.forEach{last[names.getValue(it)]=i}
            names[s.name]=i
        }
        last[last.lastIndex]=stages.size
        val free=ArrayList<Tex>()
        stages.forEachIndexed{i,s->
            for(j in 0 until i)if(last[j]==i-1)free.add(targets[j])
            val tw=w*s.scale;val th=h*s.scale
            val k=free.indexOfFirst{it.w==tw&&it.h==th}
            targets.add(if(k<0)allocate(tw,th) else free.removeAt(k))
        }
    }
    private fun bind(p:Int,name:String,unit:Int,tex:Tex){
        GL.glActiveTexture(GL.GL_TEXTURE0+unit)
        GL.glBindTexture(GL.GL_TEXTURE_2D,tex.id)
        GL.glUniform1i(GL.glGetUniformLocation(p,"u_"+name),unit)
        GL.glUniform2f(GL.glGetUniformLocation(p,"size_"+name),tex.w.toFloat(),tex.h.toFloat())
    }
    private fun video(p:Int,id:Int,matrix:FloatArray){
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,id)
        GL.glUniform1i(GL.glGetUniformLocation(p,"video"),0)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(p,"matrix"),1,false,matrix,0)
    }
    private fun draw(){
        GL.glBindVertexArray(vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP,0,4)
        GL.glBindVertexArray(0)
    }
    fun render(video:Int,matrix:FloatArray,w:Int,h:Int,outW:Int,outH:Int,reuse:Boolean){
        ensure(w,h)
        if(!(reuse&&valid&&lastVideo==video&&lastMatrix.contentEquals(matrix))){
            val y=luma!!
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,fbo)
            GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER,GL.GL_COLOR_ATTACHMENT0,GL.GL_TEXTURE_2D,y.id,0)
            check(GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)==GL.GL_FRAMEBUFFER_COMPLETE)
            GL.glViewport(0,0,w,h);GL.glUseProgram(extract);video(extract,video,matrix);draw()
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,0)
            C.glMemoryBarrier(C.GL_FRAMEBUFFER_BARRIER_BIT or C.GL_TEXTURE_FETCH_BARRIER_BIT)
            val names=HashMap<String,Tex>();names["LUMA"]=y
            stages.forEachIndexed{i,s->
                val t=targets[i]
                GL.glUseProgram(s.program)
                s.inputs.forEachIndexed{unit,n->bind(s.program,n,unit,names.getValue(n))}
                GL.glUniform2i(GL.glGetUniformLocation(s.program,"outputSize"),t.w,t.h)
                C.glBindImageTexture(0,t.id,0,false,0,C.GL_WRITE_ONLY,GL.GL_RGBA16F)
                C.glDispatchCompute((t.w+s.tw-1)/s.tw,(t.h+s.th-1)/s.th,1)
                C.glMemoryBarrier(C.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT or C.GL_TEXTURE_FETCH_BARRIER_BIT)
                names[s.name]=t
            }
            C.glBindImageTexture(0,0,0,false,0,C.GL_WRITE_ONLY,GL.GL_RGBA16F)
            valid=true;lastVideo=video;matrix.copyInto(lastMatrix)
        }
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,0)
        GL.glViewport(0,0,outW,outH);GL.glUseProgram(composite)
        video(composite,video,matrix)
        GL.glActiveTexture(GL.GL_TEXTURE1);GL.glBindTexture(GL.GL_TEXTURE_2D,targets.last().id)
        GL.glUniform1i(GL.glGetUniformLocation(composite,"learned"),1)
        draw()
        val err=GL.glGetError()
        check(err==GL.GL_NO_ERROR){"Compute GL error 0x"+err.toString(16)}
    }
    fun close(){
        release();stages.forEach{GL.glDeleteProgram(it.program)};stages.clear()
        GL.glDeleteProgram(extract);GL.glDeleteProgram(composite)
        GL.glDeleteFramebuffers(1,intArrayOf(fbo),0);GL.glDeleteVertexArrays(1,intArrayOf(vao),0)
    }
}
