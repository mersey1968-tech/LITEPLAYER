package com.example.liteplayer

import android.opengl.GLES30 as G
import android.opengl.GLES11Ext

/** Causal motion-compensated reconstruction experiment, 1280x720 SDR only. */
internal class Temporal720 {
    private data class Target(val tex:Int,val fbo:Int,val w:Int,val h:Int)
    private val targets=ArrayList<Target>()
    private val programs=ArrayList<Int>()
    private var index=0
    private var valid=false
    private var lastTime=0L
    private var lastW=0
    private var lastH=0
    private val vertex="""#version 300 es
        out vec2 uv;
        void main(){vec2 p=vec2(float(gl_VertexID&1),float(gl_VertexID>>1));
          uv=p;gl_Position=vec4(p*2.-1.,0.,1.);}
    """
    private fun program(f:String):Int {
        fun compile(type:Int,s:String):Int {
            val id=G.glCreateShader(type); G.glShaderSource(id,s);G.glCompileShader(id)
            val ok=IntArray(1);G.glGetShaderiv(id,G.GL_COMPILE_STATUS,ok,0)
            if(ok[0]!=1){val msg=G.glGetShaderInfoLog(id);G.glDeleteShader(id);error(msg)}
            return id
        }
        val v=compile(G.GL_VERTEX_SHADER,vertex);val fs=compile(G.GL_FRAGMENT_SHADER,f)
        val id=G.glCreateProgram();G.glAttachShader(id,v);G.glAttachShader(id,fs);G.glLinkProgram(id)
        G.glDeleteShader(v);G.glDeleteShader(fs)
        val ok=IntArray(1);G.glGetProgramiv(id,G.GL_LINK_STATUS,ok,0)
        if(ok[0]!=1){val msg=G.glGetProgramInfoLog(id);G.glDeleteProgram(id);error(msg)}
        programs.add(id);return id
    }
    private val capture=program("""#version 300 es
        #extension GL_OES_EGL_image_external_essl3 : require
        precision highp float;in vec2 uv;out vec4 color;
        uniform samplerExternalOES video;uniform mat4 matrix;
        void main(){color=vec4(texture(video,(matrix*vec4(uv,0.,1.)).xy).rgb,1.);}
    """)
    private val motion=program("""#version 300 es
        precision highp float;in vec2 uv;out vec4 color;
        uniform sampler2D cur,old;
        const vec2 pt=vec2(1./1280.,1./720.);
        float y(vec3 c){return dot(c,vec3(.2126,.7152,.0722));}
        float cost(vec2 d,vec4 a,float center){
            vec2 q=uv+d*pt;
            vec4 b=vec4(y(texture(old,q+vec2(2.,0.)*pt).rgb),y(texture(old,q-vec2(2.,0.)*pt).rgb),
                        y(texture(old,q+vec2(0.,2.)*pt).rgb),y(texture(old,q-vec2(0.,2.)*pt).rgb));
            return dot(abs(a-b),vec4(.2))+.2*abs(center-y(texture(old,q).rgb))+.001*length(d);
        }
        void main(){
            float c=y(texture(cur,uv).rgb);
            vec4 a=vec4(y(texture(cur,uv+vec2(2.,0.)*pt).rgb),y(texture(cur,uv-vec2(2.,0.)*pt).rgb),
                        y(texture(cur,uv+vec2(0.,2.)*pt).rgb),y(texture(cur,uv-vec2(0.,2.)*pt).rgb));
            float best=cost(vec2(0.),a,c);vec2 d=vec2(0.);
            for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
                vec2 test=vec2(float(i),float(j))*2.;
                float e=cost(test,a,c);
                if(e<best){best=e;d=test;}
            }
            float l=cost(d-vec2(1.,0.),a,c),r=cost(d+vec2(1.,0.),a,c);
            float b=cost(d-vec2(0.,1.),a,c),t=cost(d+vec2(0.,1.),a,c);
            vec2 denom=max(vec2(l+r,b+t)-2.*best,vec2(.004));
            vec2 refine=clamp(.5*vec2(l-r,b-t)/denom,-.75,.75);
            float confidence=(1.-smoothstep(.018,.065,best))*smoothstep(.012,.075,max(abs(a.x-a.y),abs(a.z-a.w)));
            color=vec4(d+refine,confidence,1.);
        }
    """)
    private val reconstruct=program("""#version 300 es
        precision highp float;in vec2 uv;out vec4 color;
        uniform sampler2D cur,old,flow,history;uniform float ready;
        const vec2 pt=vec2(1./1280.,1./720.);
        float y(vec3 c){return dot(c,vec3(.2126,.7152,.0722));}
        void main(){
            vec3 c=texture(cur,uv).rgb;
            float l=y(texture(cur,uv-vec2(pt.x,0.)).rgb),r=y(texture(cur,uv+vec2(pt.x,0.)).rgb);
            float b=y(texture(cur,uv-vec2(0.,pt.y)).rgb),t=y(texture(cur,uv+vec2(0.,pt.y)).rgb);
            float lum=y(c),lo=min(lum,min(min(l,r),min(b,t))),hi=max(lum,max(max(l,r),max(b,t)));
            float detail=lum-.25*(l+r+b+t);
            float base=clamp(lum+1.105*detail,lo-.036,hi+.036);
            float result=base;
            if(ready>.5){
                vec3 m=texture(flow,uv).rgb;vec2 q=uv+m.xy*pt;
                float prior=y(texture(history,q).rgb);
                float observed=y(texture(old,q).rgb);
                float residual=abs(observed-lum);
                float fractional=length(fract(m.xy+.5)-.5);
                float trust=m.z*(1.-smoothstep(.016,.070,residual))*smoothstep(.04,.32,fractional);
                if(any(lessThan(q,pt))||any(greaterThan(q,1.-pt)))trust=0.;
                result=mix(base,clamp(prior,lo-.036,hi+.036),.52*trust);
                vec2 sampleCenter=(floor(q/pt)+.5)*pt;
                float innovation=y(texture(old,sampleCenter).rgb)-observed;
                float proximity=1.-smoothstep(.10,.70,length((q-sampleCenter)/pt));
                result=clamp(result+trust*proximity*.82*innovation,lo-.045,hi+.045);
            }
            vec3 rgb=clamp(c+vec3(result-lum),0.,1.);
            float Y=y(rgb);vec3 chroma=rgb-vec3(Y);
            color=vec4(clamp(rgb+.18*chroma+vec3(.23*Y*(1.-Y)*(2.*Y-1.)),0.,1.),1.);
        }
    """)
    // Display-only shadow correction: never feed adjusted blacks into temporal history.
    private val present=program("""#version 300 es
        precision highp float;in vec2 uv;out vec4 color;
        uniform sampler2D image;
        void main(){
            vec3 rgb=texture(image,uv).rgb;
            float Y=dot(rgb,vec3(.2126,.7152,.0722));
            float scale=1.-.12*(1.-smoothstep(0.,.28,Y));
            color=vec4(rgb*scale,1.);
        }
    """)
    private fun target(w:Int,h:Int,fp:Boolean=false):Target {
        val ids=IntArray(1);G.glGenTextures(1,ids,0);val tex=ids[0]
        G.glBindTexture(G.GL_TEXTURE_2D,tex)
        G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MIN_FILTER,G.GL_LINEAR)
        G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MAG_FILTER,G.GL_LINEAR)
        G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_S,G.GL_CLAMP_TO_EDGE)
        G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_T,G.GL_CLAMP_TO_EDGE)
        G.glTexImage2D(G.GL_TEXTURE_2D,0,if(fp)G.GL_RGBA16F else G.GL_RGBA8,w,h,0,G.GL_RGBA,if(fp)G.GL_HALF_FLOAT else G.GL_UNSIGNED_BYTE,null)
        G.glGenFramebuffers(1,ids,0);val fbo=ids[0]
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,fbo)
        G.glFramebufferTexture2D(G.GL_FRAMEBUFFER,G.GL_COLOR_ATTACHMENT0,G.GL_TEXTURE_2D,tex,0)
        val t=Target(tex,fbo,w,h);targets.add(t)
        check(G.glCheckFramebufferStatus(G.GL_FRAMEBUFFER)==G.GL_FRAMEBUFFER_COMPLETE)
        return t
    }
    private fun bind(p:Int,name:String,unit:Int,tex:Int,external:Boolean=false){
        G.glActiveTexture(G.GL_TEXTURE0+unit)
        G.glBindTexture(if(external)GLES11Ext.GL_TEXTURE_EXTERNAL_OES else G.GL_TEXTURE_2D,tex)
        G.glUniform1i(G.glGetUniformLocation(p,name),unit)
    }
    private fun begin(p:Int,t:Target){
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,t.fbo);G.glViewport(0,0,t.w,t.h);G.glUseProgram(p)
    }
    private fun draw(){G.glDrawArrays(G.GL_TRIANGLE_STRIP,0,4)}
    private fun releaseTargets(){
        targets.forEach{G.glDeleteTextures(1,intArrayOf(it.tex),0);G.glDeleteFramebuffers(1,intArrayOf(it.fbo),0)}
        targets.clear();valid=false
    }
    private fun ensure(w:Int,h:Int){
        if(targets.size==5 && lastW==w && lastH==h)return
        releaseTargets();lastW=w;lastH=h;index=0
        repeat(2){target(1280,720)}
        target(320,180,true)
        repeat(2){target(w,h)}
    }
    fun invalidate(){valid=false}
    fun render(video:Int,matrix:FloatArray,w:Int,h:Int,timestamp:Long,newFrame:Boolean){
        ensure(w,h)
        if(newFrame || !valid){
            val current=targets[index];val old=targets[1-index];val flow=targets[2]
            val out=targets[3+index];val history=targets[3+1-index]
            val ready=valid && timestamp>lastTime && timestamp-lastTime<150000000L
            begin(capture,current);bind(capture,"video",0,video,true)
            G.glUniformMatrix4fv(G.glGetUniformLocation(capture,"matrix"),1,false,matrix,0);draw()
            if(ready){
                begin(motion,flow);bind(motion,"cur",0,current.tex);bind(motion,"old",1,old.tex);draw()
            }
            begin(reconstruct,out);bind(reconstruct,"cur",0,current.tex);bind(reconstruct,"old",1,old.tex)
            bind(reconstruct,"flow",2,flow.tex);bind(reconstruct,"history",3,history.tex)
            G.glUniform1f(G.glGetUniformLocation(reconstruct,"ready"),if(ready)1f else 0f);draw()
            lastTime=timestamp;valid=true;index=1-index
        }
        val out=targets[3+1-index]
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,0)
        G.glViewport(0,0,w,h)
        G.glUseProgram(present)
        bind(present,"image",0,out.tex)
        draw()
        check(G.glGetError()==G.GL_NO_ERROR){"Temporal GPU render failed"}
    }
    fun close(){releaseTargets();programs.forEach{G.glDeleteProgram(it)};programs.clear()}
}
