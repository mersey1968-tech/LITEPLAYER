package com.example.liteplayer

import android.content.Context
import android.opengl.GLES31 as G
import android.opengl.GLES11Ext
import java.nio.ByteBuffer
import java.nio.ByteOrder

internal class ArtCNN(context: Context) {
    private val fbo=IntArray(1)
    private var w=0
    private var h=0
    private var valid=false
    private val quad=ByteBuffer.allocateDirect(32).order(ByteOrder.nativeOrder()).asFloatBuffer().apply{
        put(floatArrayOf(-1f,-1f,1f,-1f,-1f,1f,1f,1f));position(0)
    }
    private val vertex="#version 300 es\nlayout(location=0) in vec2 p; out vec2 uv; void main(){uv=p*.5+.5;gl_Position=vec4(p,0.,1.);}"
    private val capture=graphics("""#version 300 es
#extension GL_OES_EGL_image_external_essl3 : require
precision highp float;
in vec2 uv;out vec4 color;
uniform samplerExternalOES video;
uniform mat4 transform;
void main(){color=texture(video,(transform*vec4(uv,0.,1.)).xy);}
""")
    private val present=graphics("""#version 300 es
precision highp float;
in vec2 uv;out vec4 color;
uniform sampler2D original;
uniform sampler2D restored;
void main(){
vec3 rgb=texture(original,uv).rgb;
float y=dot(rgb,vec3(.2126,.7152,.0722));
float newY=texture(restored,uv).r;
float delta=newY-y;
float strength=mix(2.5,1.25,smoothstep(.035,.12,abs(delta)));
float enhanced=clamp(y+delta*strength,0.,1.);
color=vec4(clamp(rgb+vec3(enhanced-y),0.,1.),1.);
}
""")
    private val programs=IntArray(8){i->link(intArrayOf(compile(G.GL_COMPUTE_SHADER,context.assets.open("reflite/art"+i+".comp").bufferedReader().use{it.readText()})))}
    private val images=IntArray(6)
    init { G.glGenFramebuffers(1,fbo,0) }
    private fun compile(type:Int,s:String):Int{
        val id=G.glCreateShader(type);G.glShaderSource(id,s);G.glCompileShader(id)
        val status=IntArray(1);G.glGetShaderiv(id,G.GL_COMPILE_STATUS,status,0)
        check(status[0]==G.GL_TRUE){G.glGetShaderInfoLog(id)}
        return id
    }
    private fun link(shaders:IntArray):Int{
        val p=G.glCreateProgram();for(s in shaders)G.glAttachShader(p,s);G.glLinkProgram(p)
        val status=IntArray(1);G.glGetProgramiv(p,G.GL_LINK_STATUS,status,0)
        for(s in shaders)G.glDeleteShader(s)
        check(status[0]==G.GL_TRUE){G.glGetProgramInfoLog(p)}
        return p
    }
    private fun graphics(fs:String)=link(intArrayOf(compile(G.GL_VERTEX_SHADER,vertex),compile(G.GL_FRAGMENT_SHADER,fs)))
    private fun draw(){
        quad.position(0);G.glEnableVertexAttribArray(0);G.glVertexAttribPointer(0,2,G.GL_FLOAT,false,0,quad)
        G.glDrawArrays(G.GL_TRIANGLE_STRIP,0,4);G.glDisableVertexAttribArray(0)
    }
    private fun allocate(width:Int,height:Int){
        w=width;h=height;valid=false
        G.glDeleteTextures(6,images,0);G.glGenTextures(6,images,0)
        for(i in images.indices){
            G.glBindTexture(G.GL_TEXTURE_2D,images[i])
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MIN_FILTER,G.GL_LINEAR)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MAG_FILTER,G.GL_LINEAR)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_S,G.GL_CLAMP_TO_EDGE)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_T,G.GL_CLAMP_TO_EDGE)
            G.glTexStorage2D(G.GL_TEXTURE_2D,1,if(i==0)G.GL_RGBA8 else G.GL_RGBA16F,if(i in 1..3 || i==5)2*w else w,if(i in 1..3 || i==5)2*h else h)
        }
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,fbo[0])
        G.glFramebufferTexture2D(G.GL_FRAMEBUFFER,G.GL_COLOR_ATTACHMENT0,G.GL_TEXTURE_2D,images[0],0)
        check(G.glCheckFramebufferStatus(G.GL_FRAMEBUFFER)==G.GL_FRAMEBUFFER_COMPLETE)
        checkGl("allocation")
    }
    private fun checkGl(stage:String){
        val error=G.glGetError()
        check(error==G.GL_NO_ERROR){"ArtCNN "+stage+" GL 0x"+Integer.toHexString(error)}
    }
    private fun stage(n:Int,src:Int,dst:Int,skip:Int=0){
        val p=programs[n];G.glUseProgram(p)
        G.glActiveTexture(G.GL_TEXTURE0);G.glBindTexture(G.GL_TEXTURE_2D,images[src])
        G.glUniform1i(G.glGetUniformLocation(p,"sourceTex"),0)
        if(n==6){
            G.glActiveTexture(G.GL_TEXTURE1);G.glBindTexture(G.GL_TEXTURE_2D,images[skip])
            G.glUniform1i(G.glGetUniformLocation(p,"skipTex"),1)
        }
        G.glUniform2i(G.glGetUniformLocation(p,"size"),w,h)
        G.glBindImageTexture(0,images[dst],0,false,0,G.GL_WRITE_ONLY,G.GL_RGBA16F)
        checkGl("stage "+n+" binding")
        if(n in 1..5) G.glDispatchCompute((w+7)/8,(h+7)/8,1)
        else G.glDispatchCompute(((if(n==7)2*w else w)+7)/8,((if(n==7)2*h else h)+7)/8,1)
        checkGl("stage "+n+" dispatch")
        G.glMemoryBarrier(G.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT or G.GL_TEXTURE_FETCH_BARRIER_BIT)
    }
    fun render(video:Int,matrix:FloatArray,width:Int,height:Int,outW:Int,outH:Int,newFrame:Boolean){
        if(w!=width||h!=height)allocate(width,height)
        if(newFrame||!valid){
            G.glBindFramebuffer(G.GL_FRAMEBUFFER,fbo[0]);G.glViewport(0,0,w,h);G.glUseProgram(capture)
            G.glActiveTexture(G.GL_TEXTURE0);G.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,video)
            G.glUniform1i(G.glGetUniformLocation(capture,"video"),0)
            G.glUniformMatrix4fv(G.glGetUniformLocation(capture,"transform"),1,false,matrix,0);draw()
            G.glBindFramebuffer(G.GL_FRAMEBUFFER,0)
            stage(0,0,1)
            stage(1,1,2);stage(2,2,3);stage(3,3,2);stage(4,2,3);stage(5,3,2)
            stage(6,2,4,1);stage(7,4,5)
            valid=true
        }
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,0);G.glViewport(0,0,outW,outH);G.glUseProgram(present)
        G.glActiveTexture(G.GL_TEXTURE0);G.glBindTexture(G.GL_TEXTURE_2D,images[0])
        G.glUniform1i(G.glGetUniformLocation(present,"original"),0)
        G.glActiveTexture(G.GL_TEXTURE1);G.glBindTexture(G.GL_TEXTURE_2D,images[5])
        G.glUniform1i(G.glGetUniformLocation(present,"restored"),1);draw()
        checkGl("presentation")
    }
    fun close(){
        G.glDeleteTextures(6,images,0);G.glDeleteFramebuffers(1,fbo,0)
        G.glDeleteProgram(capture);G.glDeleteProgram(present);programs.forEach{G.glDeleteProgram(it)}
    }
}
