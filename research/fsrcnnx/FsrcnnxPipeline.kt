package com.example.liteplayer

import android.opengl.GLES11Ext
import android.opengl.GLES30
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** FSRCNNX x2 8-0-4-1: 14 pretrained OpenGL ES inference stages. */
internal class FsrcnnxPipeline(raw: String) {
    private data class Stage(val inputs: List<String>, val output: String, val scaled: Boolean, val program: Int)
    private data class Target(val texture: Int, val fbo: Int, val w: Int, val h: Int)
    private val stages = mutableListOf<Stage>()
    private val targets = mutableListOf<Target>()
    private val vertices=ByteBuffer.allocateDirect(32).order(ByteOrder.nativeOrder()).asFloatBuffer()
        .apply { put(floatArrayOf(-1f,-1f,1f,-1f,-1f,1f,1f,1f));position(0) }
    private var composite=0
    private var allocatedW=0
    private var allocatedH=0
    private val vertexShader="""#version 300 es
        in vec2 position;out vec2 uv;
        void main(){uv=position*0.5+0.5;gl_Position=vec4(position,0.,1.);}
    """
    init {
        val sections=raw.split("//!HOOK ").drop(1)
        check(sections.size==14){"Expected complete 14-stage FSRCNNX network"}
        for(section in sections) {
            val header=section.substringBefore("vec4 hook()")
            val binds=Regex("//!BIND ([A-Z0-9]+)").findAll(header).map{it.groupValues[1]}.toList()
            val save=Regex("//!SAVE ([A-Z0-9]+)").find(header)?.groupValues?.get(1)?:"FINAL"
            val scaled=header.contains("//!WIDTH")
            val defs=StringBuilder()
            for(name in binds) {
                if(name=="LUMA") {
                    defs.append("uniform samplerExternalOES u_LUMA;uniform mat4 uMatrix;\n")
                    defs.append("float LUMA_texOff(vec2 d){vec3 c=texture(u_LUMA,(uMatrix*vec4(uv+d/uSize,0.,1.)).xy).rgb;return dot(c,vec3(0.2126,0.7152,0.0722));}\n")
                    defs.append("float LUMA_texOff(int n){return LUMA_texOff(vec2(0.));}\n")
                } else {
                    defs.append("uniform sampler2D u_").append(name).append(";\n")
                    defs.append("vec4 ").append(name).append("_texOff(vec2 d){return texture(u_").append(name).append(",uv+d/uSize);}\n")
                    defs.append("vec4 ").append(name).append("_texOff(int n){return texture(u_").append(name).append(",uv);}\n")
                    defs.append("vec4 ").append(name).append("_tex(vec2 p){return texture(u_").append(name).append(",p);}\n")
                    defs.append("#define ").append(name).append("_pos uv\n#define ").append(name).append("_size uSize\n#define ").append(name).append("_pt (1.0/uSize)\n")
                }
            }
            val fragment="#version 300 es\n"+
                (if(binds.contains("LUMA"))"#extension GL_OES_EGL_image_external_essl3 : require\n" else "")+
                "precision highp float;in vec2 uv;out vec4 outputColor;uniform vec2 uSize;\n"+
                defs.toString()+"\nvec4 hook()"+section.substringAfter("vec4 hook()")+
                "\nvoid main(){outputColor=hook();}"
            stages.add(Stage(binds,save,scaled,link(vertexShader,fragment)))
        }
        composite=link(vertexShader,"""#version 300 es
            #extension GL_OES_EGL_image_external_essl3 : require
            precision highp float;
            uniform sampler2D uNeural;uniform samplerExternalOES uVideo;
            uniform mat4 uMatrix;uniform float uDiagnostic;
            uniform float uHdr;
            in vec2 uv;out vec4 outColor;
            // BT.709 linear RGB to BT.2020 linear RGB, then ST 2084 (PQ).
            vec3 sdrToHdr10(vec3 rgb) {
                vec3 linear709=pow(clamp(rgb,0.,1.),vec3(2.4));
                mat3 to2020=mat3(
                    0.627404,0.069097,0.016391,
                    0.329282,0.919540,0.088013,
                    0.043314,0.011362,0.895595);
                vec3 l2020=max(to2020*linear709,vec3(0.));
                // User-selected 1000 nit peak. Keep diffuse SDR levels
                // near 203 nits; expand only the brightest encoded highlights.
                // SDR contains no recoverable specular highlight information.
                vec3 knee=clamp((l2020-vec3(0.65))/0.35,0.,1.);
                vec3 nits=l2020*203.0+vec3(797.0)*knee*knee*knee;
                vec3 p=pow(clamp(nits/10000.0,0.,1.),vec3(2610.0/16384.0));
                return pow((vec3(3424.0/4096.0)+vec3(2413.0/128.0)*p)/
                    (vec3(1.)+vec3(2392.0/128.0)*p),vec3(2523.0/32.0));
            }
            void main(){
                float y=texture(uNeural,uv).r;
                vec3 rgb=texture(uVideo,(uMatrix*vec4(uv,0.,1.)).xy).rgb;
                float orig=dot(rgb,vec3(0.2126,0.7152,0.0722));
                vec3 reconstructed=clamp(rgb+vec3(y-orig),0.,1.);
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);
                if(uDiagnostic>0.5 && uv.x<0.2 && uv.y>0.91)
                    outColor=vec4(1.,0.,1.,1.);
            }
        """)
    }
    private fun link(v:String,f:String):Int {
        fun compile(type:Int,body:String):Int {
            val id=GLES30.glCreateShader(type);GLES30.glShaderSource(id,body);GLES30.glCompileShader(id)
            val ok=IntArray(1);GLES30.glGetShaderiv(id,GLES30.GL_COMPILE_STATUS,ok,0)
            check(ok[0]==GLES30.GL_TRUE){GLES30.glGetShaderInfoLog(id)}
            return id
        }
        val vs=compile(GLES30.GL_VERTEX_SHADER,v);val fs=compile(GLES30.GL_FRAGMENT_SHADER,f)
        val id=GLES30.glCreateProgram();GLES30.glAttachShader(id,vs);GLES30.glAttachShader(id,fs)
        GLES30.glLinkProgram(id);val ok=IntArray(1)
        GLES30.glGetProgramiv(id,GLES30.GL_LINK_STATUS,ok,0)
        GLES30.glDeleteShader(vs);GLES30.glDeleteShader(fs)
        check(ok[0]==GLES30.GL_TRUE){GLES30.glGetProgramInfoLog(id)}
        return id
    }
    private fun allocate(w:Int,h:Int):Target {
        val id=IntArray(1);GLES30.glGenTextures(1,id,0);val tex=id[0]
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,tex)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MIN_FILTER,GLES30.GL_NEAREST)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MAG_FILTER,GLES30.GL_NEAREST)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_WRAP_S,GLES30.GL_CLAMP_TO_EDGE)
        GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_WRAP_T,GLES30.GL_CLAMP_TO_EDGE)
        GLES30.glTexImage2D(GLES30.GL_TEXTURE_2D,0,GLES30.GL_RGBA16F,w,h,0,GLES30.GL_RGBA,GLES30.GL_HALF_FLOAT,null)
        GLES30.glGenFramebuffers(1,id,0);val fbo=id[0]
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,fbo)
        GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER,GLES30.GL_COLOR_ATTACHMENT0,GLES30.GL_TEXTURE_2D,tex,0)
        check(GLES30.glCheckFramebufferStatus(GLES30.GL_FRAMEBUFFER)==GLES30.GL_FRAMEBUFFER_COMPLETE){"FSRCNNX requires RGBA16F framebuffer"}
        return Target(tex,fbo,w,h)
    }
    private fun draw(program:Int) {
        val loc=GLES30.glGetAttribLocation(program,"position")
        vertices.position(0);GLES30.glEnableVertexAttribArray(loc)
        GLES30.glVertexAttribPointer(loc,2,GLES30.GL_FLOAT,false,0,vertices)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP,0,4)
        GLES30.glDisableVertexAttribArray(loc)
    }
    private fun ensureSize(w:Int,h:Int) {
        if(w==allocatedW && h==allocatedH)return
        releaseTargets();allocatedW=w;allocatedH=h
        stages.forEach { targets.add(allocate(if(it.scaled)2*w else w,if(it.scaled)2*h else h)) }
    }
    fun render(video:Int,matrix:FloatArray,w:Int,h:Int,outW:Int,outH:Int,diagnostic:Boolean,hdr:Boolean=false,outputFbo:Int=0) {
        ensureSize(w,h);val named=mutableMapOf<String,Int>()
        stages.forEachIndexed { idx,stage ->
            val t=targets[idx]
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,t.fbo)
            GLES30.glViewport(0,0,t.w,t.h)
            GLES30.glUseProgram(stage.program)
            GLES30.glUniform2f(GLES30.glGetUniformLocation(stage.program,"uSize"),w.toFloat(),h.toFloat())
            stage.inputs.forEachIndexed { unit,name ->
                val texture=if(name=="LUMA")video else named[name]?:error("Missing network input "+name)
                GLES30.glActiveTexture(GLES30.GL_TEXTURE0+unit)
                GLES30.glBindTexture(if(name=="LUMA")GLES11Ext.GL_TEXTURE_EXTERNAL_OES else GLES30.GL_TEXTURE_2D,texture)
                GLES30.glUniform1i(GLES30.glGetUniformLocation(stage.program,"u_"+name),unit)
            }
            if(stage.inputs.contains("LUMA"))
                GLES30.glUniformMatrix4fv(GLES30.glGetUniformLocation(stage.program,"uMatrix"),1,false,matrix,0)
            draw(stage.program);named[stage.output]=t.texture
        }
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,outputFbo)
        GLES30.glViewport(0,0,outW,outH);GLES30.glUseProgram(composite)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,targets.last().texture)
        GLES30.glUniform1i(GLES30.glGetUniformLocation(composite,"uNeural"),0)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE1)
        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,video)
        GLES30.glUniform1i(GLES30.glGetUniformLocation(composite,"uVideo"),1)
        GLES30.glUniformMatrix4fv(GLES30.glGetUniformLocation(composite,"uMatrix"),1,false,matrix,0)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(composite,"uDiagnostic"),if(diagnostic)1f else 0f)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(composite,"uHdr"),if(hdr)1f else 0f)
        draw(composite)
        check(GLES30.glGetError()==GLES30.GL_NO_ERROR){"FSRCNNX GPU render failed"}
    }
    private fun releaseTargets(){
        targets.forEach {
            GLES30.glDeleteTextures(1,intArrayOf(it.texture),0)
            GLES30.glDeleteFramebuffers(1,intArrayOf(it.fbo),0)
        }
        targets.clear()
    }
    fun close(){
        releaseTargets();stages.forEach{GLES30.glDeleteProgram(it.program)}
        GLES30.glDeleteProgram(composite)
    }
}
