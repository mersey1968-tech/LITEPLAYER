package com.example.liteplayer

import android.content.Context
import android.graphics.SurfaceTexture
import android.opengl.GLES11Ext
import android.opengl.GLES30
import android.opengl.GLSurfaceView
import android.util.Log
import android.view.Surface
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.atomic.AtomicBoolean
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/** Experimental unprotected 540p-1080p SDR GPU renderer. Default playback never uses this. */
class ReferenceScalerView(context: Context) : GLSurfaceView(context), GLSurfaceView.Renderer {
    @Volatile var decoderSurface: Surface? = null
        private set
    var onSurfaceReady: ((Surface) -> Unit)? = null
    var onFailure: ((String) -> Unit)? = null
    private var texVideo = 0
    private var texIntermediate = 0
    private var framebuffer = 0
    private var progHorizontal = 0
    private var progVertical = 0
    private var surfaceTexture: SurfaceTexture? = null
    private val pending = AtomicBoolean(false)
    private val transform = FloatArray(16)
    private var srcW = 1920
    private var srcH = 1080
    private var outW = 0
    private var outH = 0
    private var allocatedW = 0
    private var allocatedH = 0
    private var failed = false
    @Volatile private var diagnosticEnabled = false

    fun setDiagnostic(enabled: Boolean) {
        diagnosticEnabled = enabled
        requestRender()
    }
    private val vertices = ByteBuffer.allocateDirect(32).order(ByteOrder.nativeOrder()).asFloatBuffer()
        .apply { put(floatArrayOf(-1f,-1f, 1f,-1f, -1f,1f, 1f,1f)); position(0) }

    init {
        setEGLContextClientVersion(3)
        setRenderer(this)
        renderMode = RENDERMODE_WHEN_DIRTY
        setZOrderMediaOverlay(true)
        holder.setFixedSize(3840,2160)
    }

    fun setSourceSize(w: Int, h: Int) {
        if (w !in 1..1920 || h !in 1..1080 || (w < 960 && h < 540)) return
        queueEvent { srcW = w; srcH = h; allocatedW = 0 }
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        try {
            failed = false
            val ids = IntArray(1)
            GLES30.glGenTextures(1,ids,0)
            texVideo = ids[0]
            GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,texVideo)
            for (p in intArrayOf(GLES30.GL_TEXTURE_MIN_FILTER,GLES30.GL_TEXTURE_MAG_FILTER))
                GLES30.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,p,GLES30.GL_LINEAR)
            progHorizontal = link(shaderVertex,shaderHorizontal)
            progVertical = link(shaderVertex,shaderVertical)
            surfaceTexture = SurfaceTexture(texVideo).also { st ->
                st.setOnFrameAvailableListener { pending.set(true); requestRender() }
            }
            val s = Surface(surfaceTexture)
            decoderSurface = s
            post { onSurfaceReady?.invoke(s) }
        } catch (ex: Throwable) { fail("GPU initialization failed: " + ex.message) }
    }

    override fun onSurfaceChanged(gl: GL10?, w: Int, h: Int) {
        outW = w
        outH = h
    }

    override fun onDrawFrame(gl: GL10?) {
        if (failed || outW < 1 || outH < 1) return
        try {
            if (pending.getAndSet(false)) {
                surfaceTexture?.updateTexImage()
                surfaceTexture?.getTransformMatrix(transform)
            }
            ensureFramebuffer(outW,srcH)
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,framebuffer)
            GLES30.glViewport(0,0,outW,srcH)
            pass(progHorizontal,texVideo,GLES11Ext.GL_TEXTURE_EXTERNAL_OES,srcW,srcH,transform)
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,0)
            GLES30.glViewport(0,0,outW,outH)
            pass(progVertical,texIntermediate,GLES30.GL_TEXTURE_2D,outW,srcH,identity)
        } catch (ex: Throwable) { fail("GPU rendering failed: " + ex.message) }
    }

    private fun ensureFramebuffer(w:Int,h:Int) {
        if (allocatedW == w && allocatedH == h) return
        if (texIntermediate!=0) GLES30.glDeleteTextures(1,intArrayOf(texIntermediate),0)
        if (framebuffer!=0) GLES30.glDeleteFramebuffers(1,intArrayOf(framebuffer),0)
        val ids=IntArray(1)
        GLES30.glGenTextures(1,ids,0);texIntermediate=ids[0]
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,texIntermediate)
        GLES30.glTexImage2D(GLES30.GL_TEXTURE_2D,0,GLES30.GL_RGBA8,w,h,0,GLES30.GL_RGBA,GLES30.GL_UNSIGNED_BYTE,null)
        for (p in intArrayOf(GLES30.GL_TEXTURE_MIN_FILTER,GLES30.GL_TEXTURE_MAG_FILTER))
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,p,GLES30.GL_LINEAR)
        GLES30.glGenFramebuffers(1,ids,0);framebuffer=ids[0]
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,framebuffer)
        GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER,GLES30.GL_COLOR_ATTACHMENT0,
            GLES30.GL_TEXTURE_2D,texIntermediate,0)
        check(GLES30.glCheckFramebufferStatus(GLES30.GL_FRAMEBUFFER)==GLES30.GL_FRAMEBUFFER_COMPLETE)
        allocatedW=w;allocatedH=h
    }

    private fun pass(program:Int,texture:Int,target:Int,w:Int,h:Int,matrix:FloatArray) {
        GLES30.glUseProgram(program)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glBindTexture(target,texture)
        GLES30.glUniform1i(GLES30.glGetUniformLocation(program,"video"),0)
        GLES30.glUniform2f(GLES30.glGetUniformLocation(program,"inputSize"),w.toFloat(),h.toFloat())
        GLES30.glUniform1f(GLES30.glGetUniformLocation(program,"diagnostic"),if (diagnosticEnabled) 1f else 0f)
        GLES30.glUniformMatrix4fv(GLES30.glGetUniformLocation(program,"texMatrix"),1,false,matrix,0)
        val loc=GLES30.glGetAttribLocation(program,"position")
        vertices.position(0)
        GLES30.glEnableVertexAttribArray(loc)
        GLES30.glVertexAttribPointer(loc,2,GLES30.GL_FLOAT,false,0,vertices)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP,0,4)
        GLES30.glDisableVertexAttribArray(loc)
    }

    private fun link(vertex:String,fragment:String):Int {
        fun compile(type:Int,src:String):Int {
            val s=GLES30.glCreateShader(type)
            GLES30.glShaderSource(s,src)
            GLES30.glCompileShader(s)
            val ok=IntArray(1);GLES30.glGetShaderiv(s,GLES30.GL_COMPILE_STATUS,ok,0)
            check(ok[0]==GLES30.GL_TRUE) { GLES30.glGetShaderInfoLog(s) }
            return s
        }
        val v=compile(GLES30.GL_VERTEX_SHADER,vertex)
        val f=compile(GLES30.GL_FRAGMENT_SHADER,fragment)
        val p=GLES30.glCreateProgram()
        GLES30.glAttachShader(p,v);GLES30.glAttachShader(p,f);GLES30.glLinkProgram(p)
        val ok=IntArray(1);GLES30.glGetProgramiv(p,GLES30.GL_LINK_STATUS,ok,0)
        check(ok[0]==GLES30.GL_TRUE) { GLES30.glGetProgramInfoLog(p) }
        GLES30.glDeleteShader(v);GLES30.glDeleteShader(f)
        return p
    }

    private fun fail(msg:String) {
        failed=true
        Log.e("Reflite GPU",msg)
        post { onFailure?.invoke(msg) }
    }

    fun close() {
        onSurfaceReady=null
        val old=decoderSurface;decoderSurface=null
        old?.release()
        queueEvent {
            surfaceTexture?.setOnFrameAvailableListener(null)
            surfaceTexture?.release()
            surfaceTexture=null
        }
    }

    companion object {
        private val identity=floatArrayOf(1f,0f,0f,0f,0f,1f,0f,0f,0f,0f,1f,0f,0f,0f,0f,1f)
        private val shaderVertex="""#version 300 es
            in vec2 position;out vec2 uv;
            void main(){uv=position*0.5+0.5;gl_Position=vec4(position,0.0,1.0);}
        """
        private val common="""
            precision highp float;
            in vec2 uv;out vec4 colorOut;
            uniform vec2 inputSize;uniform mat4 texMatrix;
            uniform float diagnostic;
            const float PI=3.141592653589793;
            float kernel(float x){
                float a=abs(x);
                if(a>=3.0)return 0.0;
                float px=PI*0.96*x;
                float sinc=abs(px)<0.00001?1.0:sin(px)/px;
                float window=0.42+0.5*cos(PI*a/3.0)+0.08*cos(2.0*PI*a/3.0);
                return sinc*window;
            }
        """
        private val shaderHorizontal="""#version 300 es
            #extension GL_OES_EGL_image_external_essl3 : require
            precision highp float;
            uniform samplerExternalOES video;
        """+common+"""
            vec3 sampleVideo(vec2 st){return texture(video,(texMatrix*vec4(st,0.0,1.0)).xy).rgb;}
            void main(){
                float pos=uv.x*inputSize.x-0.5;
                float base=floor(pos),frac=pos-base;
                vec3 sum=vec3(0.0);float total=0.0;
                for(int k=-2;k<=3;k++){
                    float weight=kernel(float(k)-frac);
                    sum+=weight*sampleVideo(vec2((base+float(k)+0.5)/inputSize.x,uv.y));
                    total+=weight;
                }
                vec3 outputColor=sum/max(total,0.00001);
                vec3 a=sampleVideo(vec2((base+0.5)/inputSize.x,uv.y));
                vec3 b=sampleVideo(vec2((base+1.5)/inputSize.x,uv.y));
                colorOut=vec4(mix(outputColor,clamp(outputColor,min(a,b),max(a,b)),0.65),1.0);
            }
        """
        private val shaderVertical="""#version 300 es
            precision highp float;
            uniform sampler2D video;
        """+common+"""
            void main(){
                float pos=uv.y*inputSize.y-0.5;
                float base=floor(pos),frac=pos-base;
                vec3 sum=vec3(0.0);float total=0.0;
                for(int k=-2;k<=3;k++){
                    float weight=kernel(float(k)-frac);
                    sum+=weight*texture(video,vec2(uv.x,(base+float(k)+0.5)/inputSize.y)).rgb;
                    total+=weight;
                }
                vec3 outputColor=sum/max(total,0.00001);
                vec3 a=texture(video,vec2(uv.x,(base+0.5)/inputSize.y)).rgb;
                vec3 b=texture(video,vec2(uv.x,(base+1.5)/inputSize.y)).rgb;
                colorOut=vec4(mix(outputColor,clamp(outputColor,min(a,b),max(a,b)),0.65),1.0);
                // Proof that the actual final framebuffer is generated by Reflite.
                // Only the explicit DIAGNOSTIC menu option can display this marker.
                if (diagnostic > 0.5 && uv.x < 0.20 && uv.y > 0.91)
                    colorOut=vec4(1.0,0.0,1.0,1.0);
            }
        """
    }
}
