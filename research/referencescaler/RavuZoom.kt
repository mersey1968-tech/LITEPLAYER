package com.example.liteplayer

import android.content.Context
import android.opengl.GLES31 as G
import android.opengl.GLES11Ext
import java.nio.ByteBuffer
import java.nio.ByteOrder

internal class RavuZoom(context: Context) {
    private val textures = IntArray(2)
    private val program: Int
    private val compute: Int
    private val output = IntArray(1)
    private var ow=0
    private var oh=0
    private val vertices=ByteBuffer.allocateDirect(32).order(ByteOrder.nativeOrder()).asFloatBuffer()
        .apply { put(floatArrayOf(-1f,-1f,1f,-1f,-1f,1f,1f,1f)); position(0) }
    private fun compile(type:Int, source:String):Int {
        val id=G.glCreateShader(type)
        G.glShaderSource(id,source); G.glCompileShader(id)
        val status=IntArray(1); G.glGetShaderiv(id,G.GL_COMPILE_STATUS,status,0)
        check(status[0]==G.GL_TRUE){G.glGetShaderInfoLog(id)}
        return id
    }
    init {
        val vs=compile(G.GL_VERTEX_SHADER,"#version 300 es\nin vec2 position; out vec2 uv; void main(){ uv=position*.5+.5; gl_Position=vec4(position,0.,1.); }")
        val fs=compile(G.GL_FRAGMENT_SHADER,"#version 300 es\nprecision highp float; uniform sampler2D result; out vec4 colorOut; void main(){colorOut=texelFetch(result,ivec2(gl_FragCoord.xy),0);}")
        program=G.glCreateProgram(); G.glAttachShader(program,vs); G.glAttachShader(program,fs); G.glLinkProgram(program)
        val status=IntArray(1); G.glGetProgramiv(program,G.GL_LINK_STATUS,status,0)
        G.glDeleteShader(vs); G.glDeleteShader(fs)
        check(status[0]==G.GL_TRUE){G.glGetProgramInfoLog(program)}
        val cs=compile(G.GL_COMPUTE_SHADER,context.assets.open("reflite/ravu.comp").bufferedReader().use{it.readText()})
        compute=G.glCreateProgram(); G.glAttachShader(compute,cs); G.glLinkProgram(compute)
        G.glGetProgramiv(compute,G.GL_LINK_STATUS,status,0); G.glDeleteShader(cs)
        check(status[0]==G.GL_TRUE){G.glGetProgramInfoLog(compute)}
        G.glGenTextures(1,output,0)
        G.glGenTextures(2,textures,0)
        for(i in textures.indices) {
            val bytes=context.assets.open("reflite/ravu"+i+".bin").use{it.readBytes()}
            val data=ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.LITTLE_ENDIAN).apply{put(bytes);position(0)}
            val w=data.int; val h=data.int
            val max=IntArray(1); G.glGetIntegerv(G.GL_MAX_TEXTURE_SIZE,max,0)
            check(w<=max[0] && h<=max[0]){"RAVU LUT exceeds texture limit"}
            G.glBindTexture(G.GL_TEXTURE_2D,textures[i])
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MIN_FILTER,G.GL_LINEAR)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MAG_FILTER,G.GL_LINEAR)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_S,G.GL_CLAMP_TO_EDGE)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_WRAP_T,G.GL_CLAMP_TO_EDGE)
            G.glTexImage2D(G.GL_TEXTURE_2D,0,G.GL_RGBA16F,w,h,0,G.GL_RGBA,G.GL_FLOAT,data.slice().order(ByteOrder.LITTLE_ENDIAN))
            check(G.glGetError()==G.GL_NO_ERROR){"RAVU LUT upload failed"}
        }
    }
    fun render(video:Int,matrix:FloatArray,w:Int,h:Int,outW:Int,outH:Int) {
        if(ow!=outW || oh!=outH){
            if(ow!=0){G.glDeleteTextures(1,output,0);G.glGenTextures(1,output,0)}
            G.glBindTexture(G.GL_TEXTURE_2D,output[0])
            G.glTexStorage2D(G.GL_TEXTURE_2D,1,G.GL_RGBA8,outW,outH)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MIN_FILTER,G.GL_NEAREST)
            G.glTexParameteri(G.GL_TEXTURE_2D,G.GL_TEXTURE_MAG_FILTER,G.GL_NEAREST)
            ow=outW;oh=outH
        }
        G.glUseProgram(compute)
        G.glUniform2f(G.glGetUniformLocation(compute,"uOutput"),outW.toFloat(),outH.toFloat())
        G.glActiveTexture(G.GL_TEXTURE0); G.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,video)
        G.glUniform1i(G.glGetUniformLocation(compute,"uVideo"),0)
        G.glUniform2f(G.glGetUniformLocation(compute,"uSize"),w.toFloat(),h.toFloat())
        G.glUniformMatrix4fv(G.glGetUniformLocation(compute,"uMatrix"),1,false,matrix,0)
        for(i in textures.indices) {
            G.glActiveTexture(G.GL_TEXTURE1+i); G.glBindTexture(G.GL_TEXTURE_2D,textures[i])
            G.glUniform1i(G.glGetUniformLocation(compute,if(i==0)"ravu_zoom_lut3" else "ravu_zoom_lut3_ar"),i+1)
        }
        G.glBindImageTexture(0,output[0],0,false,0,G.GL_WRITE_ONLY,G.GL_RGBA8)
        G.glDispatchCompute((outW+31)/32,(outH+7)/8,1)
        G.glMemoryBarrier(G.GL_TEXTURE_FETCH_BARRIER_BIT or G.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT)
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,0);G.glViewport(0,0,outW,outH);G.glUseProgram(program)
        G.glActiveTexture(G.GL_TEXTURE0);G.glBindTexture(G.GL_TEXTURE_2D,output[0])
        G.glUniform1i(G.glGetUniformLocation(program,"result"),0)
        val loc=G.glGetAttribLocation(program,"position")
        vertices.position(0); G.glEnableVertexAttribArray(loc)
        G.glVertexAttribPointer(loc,2,G.GL_FLOAT,false,0,vertices)
        G.glDrawArrays(G.GL_TRIANGLE_STRIP,0,4); G.glDisableVertexAttribArray(loc)
        check(G.glGetError()==G.GL_NO_ERROR){"RAVU render failed"}
    }
    fun close(){ G.glDeleteTextures(2,textures,0); G.glDeleteProgram(program);G.glDeleteProgram(compute);G.glDeleteTextures(1,output,0) }
}
