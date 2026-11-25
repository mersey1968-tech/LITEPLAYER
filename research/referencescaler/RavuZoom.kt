package com.example.liteplayer

import android.content.Context
import android.opengl.GLES30 as G
import android.opengl.GLES11Ext
import java.nio.ByteBuffer
import java.nio.ByteOrder

internal class RavuZoom(context: Context) {
    private val textures = IntArray(2)
    private val program: Int
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
        val fs=compile(G.GL_FRAGMENT_SHADER,context.assets.open("reflite/ravu.frag").bufferedReader().use{it.readText()})
        program=G.glCreateProgram(); G.glAttachShader(program,vs); G.glAttachShader(program,fs); G.glLinkProgram(program)
        val status=IntArray(1); G.glGetProgramiv(program,G.GL_LINK_STATUS,status,0)
        G.glDeleteShader(vs); G.glDeleteShader(fs)
        check(status[0]==G.GL_TRUE){G.glGetProgramInfoLog(program)}
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
        G.glBindFramebuffer(G.GL_FRAMEBUFFER,0); G.glViewport(0,0,outW,outH); G.glUseProgram(program)
        G.glActiveTexture(G.GL_TEXTURE0); G.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,video)
        G.glUniform1i(G.glGetUniformLocation(program,"uVideo"),0)
        G.glUniform2f(G.glGetUniformLocation(program,"uSize"),w.toFloat(),h.toFloat())
        G.glUniformMatrix4fv(G.glGetUniformLocation(program,"uMatrix"),1,false,matrix,0)
        for(i in textures.indices) {
            G.glActiveTexture(G.GL_TEXTURE1+i); G.glBindTexture(G.GL_TEXTURE_2D,textures[i])
            G.glUniform1i(G.glGetUniformLocation(program,if(i==0)"ravu_zoom_lut2" else "ravu_zoom_lut2_ar"),i+1)
        }
        val loc=G.glGetAttribLocation(program,"position")
        vertices.position(0); G.glEnableVertexAttribArray(loc)
        G.glVertexAttribPointer(loc,2,G.GL_FLOAT,false,0,vertices)
        G.glDrawArrays(G.GL_TRIANGLE_STRIP,0,4); G.glDisableVertexAttribArray(loc)
        check(G.glGetError()==G.GL_NO_ERROR){"RAVU render failed"}
    }
    fun close(){ G.glDeleteTextures(2,textures,0); G.glDeleteProgram(program) }
}
