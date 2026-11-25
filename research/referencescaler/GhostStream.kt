package com.example.liteplayer

import android.content.Context
import android.opengl.GLES31 as G
import android.opengl.GLES11Ext
import java.nio.ByteBuffer
import java.nio.ByteOrder

internal class GhostStream(context: Context) {
    private val buffers=IntArray(4)
    private val textures=IntArray(2)
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
float y=dot(rgb,vec3(.299,.587,.114));
float newY=texture(restored,uv).r;
color=vec4(clamp(rgb+vec3(newY-y),0.,1.),1.);
}
""")
    private val compute=link(intArrayOf(compile(G.GL_COMPUTE_SHADER,context.assets.open("reflite/ghost.comp").bufferedReader().use{it.readText()})))
    private val layers=context.assets.open("reflite/ghost.layers").bufferedReader().use{r->r.readLines().map{it.split(" ").map(String::toInt)}}
    init {
        check(layers.size==11)
        G.glGenBuffers(4,buffers,0);G.glGenTextures(2,textures,0);G.glGenFramebuffers(1,fbo,0)
        val weights=context.assets.open("reflite/ghost.weights").use{it.readBytes()}
        val b=ByteBuffer.allocateDirect(weights.size).order(ByteOrder.nativeOrder()).apply{put(weights);position(0)}
        G.glBindBuffer(G.GL_SHADER_STORAGE_BUFFER,buffers[0])
        G.glBufferData(G.GL_SHADER_STORAGE_BUFFER,weights.size,b,G.GL_STATIC_DRAW)
        G.glBindBufferBase(G.GL_SHADER_STORAGE_BUFFER,0,buffers[0])
        check(G.glGetError()==G.GL_NO_ERROR){"Ghost Stream weight upload failed"}
    }
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
        for(i in 1..3){
            G.glBindBuffer(G.GL_SHADER_STORAGE_BUFFER,buffers[i])
            G.glBufferData(G.GL_SHADER_STORAGE_BUFFER,w*h*6*8,null,G.GL_DYNAMIC_DRAW)
        }
        for(i in 0..1){
            G.glBindTexture(G.GL_TEXTURE_2D,textures[i])
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MIN_FILTER,G.GL_LINEAR)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MAG_FILTER,G.GL_LINEAR)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_S,G.GL_CLAMP_TO_EDGE)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_T,G.GL_CLAMP_TO_EDGE)
            if(i==0) G.glTexImage2D(G.GL_TEXTURE_2D,0,G.GL_RGBA8,w,h,0,G.GL_RGBA,G.GL_UNSIGNED_BYTE,null)
            else G.glTexImage2D(G.GL_TEXTURE_2D,0,G.GL_RGBA16F,w*2,h*2,0,G.GL_RGBA,G.GL_HALF_FLOAT,null)
        }
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,fbo[0])
        G.glFramebufferTexture2D(G.GL_FRAMEBUFFER,G.GL_COLOR_ATTACHMENT0,G.GL_TEXTURE_2D,textures[0],0)
        check(G.glCheckFramebufferStatus(G.GL_FRAMEBUFFER)==G.GL_FRAMEBUFFER_COMPLETE)
        check(G.glGetError()==G.GL_NO_ERROR){"Ghost Stream allocation failed"}
    }
    private fun layer(n:Int,input:Int,output:Int,skip:Int,mode:Int){
        val (offset,ig,og)=layers[n]
        G.glBindBufferBase(G.GL_SHADER_STORAGE_BUFFER,1,buffers[input])
        G.glBindBufferBase(G.GL_SHADER_STORAGE_BUFFER,2,buffers[output])
        G.glBindBufferBase(G.GL_SHADER_STORAGE_BUFFER,3,buffers[skip])
        G.glUniform1i(G.glGetUniformLocation(compute,"offset"),offset)
        G.glUniform1i(G.glGetUniformLocation(compute,"inGroups"),ig)
        G.glUniform1i(G.glGetUniformLocation(compute,"outGroups"),og)
        G.glUniform1i(G.glGetUniformLocation(compute,"mode"),mode)
        G.glDispatchCompute((w+7)/8,(h+7)/8,og)
        G.glMemoryBarrier(G.GL_SHADER_STORAGE_BARRIER_BIT or G.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT or G.GL_TEXTURE_FETCH_BARRIER_BIT)
    }
    fun render(video:Int,matrix:FloatArray,width:Int,height:Int,outW:Int,outH:Int,newFrame:Boolean){
        if(w!=width||h!=height)allocate(width,height)
        if(newFrame||!valid){
            G.glBindFramebuffer(G.GL_FRAMEBUFFER,fbo[0]);G.glViewport(0,0,w,h);G.glUseProgram(capture)
            G.glActiveTexture(G.GL_TEXTURE0);G.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,video)
            G.glUniform1i(G.glGetUniformLocation(capture,"video"),0)
            G.glUniformMatrix4fv(G.glGetUniformLocation(capture,"transform"),1,false,matrix,0);draw()
            G.glBindFramebuffer(G.GL_FRAMEBUFFER,0)
            G.glUseProgram(compute)
            G.glBindBufferBase(G.GL_SHADER_STORAGE_BUFFER,0,buffers[0])
            G.glActiveTexture(G.GL_TEXTURE0);G.glBindTexture(G.GL_TEXTURE_2D,textures[0])
            G.glUniform1i(G.glGetUniformLocation(compute,"sourceRgb"),0)
            G.glUniform2i(G.glGetUniformLocation(compute,"size"),w,h)
            G.glBindImageTexture(0,textures[1],0,false,0,G.GL_WRITE_ONLY,G.GL_RGBA16F)
            layer(0,2,1,3,0)
            var src=1
            for(i in 0..3){
                val tmp=if(src==1)2 else 1
                layer(1+i*2,src,tmp,3,1)
                layer(2+i*2,tmp,3,src,2)
                // Copy-free rotation: new block result becomes the next source.
                // src may be 3, so the next iterations use the other two distinct buffers.
                src=3
                if(i<3){
                    val old=buffers[1];buffers[1]=buffers[3];buffers[3]=old;src=1
                }
            }
            layer(9,src,2,1,4)
            layer(10,2,1,3,3)
            check(G.glGetError()==G.GL_NO_ERROR){"Ghost Stream dispatch failed"}
            valid=true
        }
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,0);G.glViewport(0,0,outW,outH);G.glUseProgram(present)
        G.glActiveTexture(G.GL_TEXTURE0);G.glBindTexture(G.GL_TEXTURE_2D,textures[0])
        G.glUniform1i(G.glGetUniformLocation(present,"original"),0)
        G.glActiveTexture(G.GL_TEXTURE1);G.glBindTexture(G.GL_TEXTURE_2D,textures[1])
        G.glUniform1i(G.glGetUniformLocation(present,"restored"),1);draw()
    }
    fun close(){
        G.glDeleteBuffers(4,buffers,0);G.glDeleteTextures(2,textures,0);G.glDeleteFramebuffers(1,fbo,0)
        G.glDeleteProgram(capture);G.glDeleteProgram(present);G.glDeleteProgram(compute)
    }
}
