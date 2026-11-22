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
import javax.microedition.khronos.egl.EGL10
import javax.microedition.khronos.egl.EGLDisplay
import javax.microedition.khronos.egl.EGLSurface
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/** Experimental trained neural SDR renderer. Default playback never uses this. */
class ReferenceScalerView(context: Context, private val hdrRequested: Boolean = false) : GLSurfaceView(context), GLSurfaceView.Renderer {
    @Volatile var decoderSurface: Surface? = null
        private set
    var onSurfaceReady: ((Surface) -> Unit)? = null
    var onFailure: ((String) -> Unit)? = null
    private var texVideo = 0
    private var texIntermediate = 0
    private var framebuffer = 0
    private var neuralPipeline: FsrcnnxPipeline? = null
    @Volatile private var hdrSurfaceActive = false
    @Volatile private var hdrConfigTenBit = false
    var onHdrUnavailable: ((String) -> Unit)? = null
    @Volatile private var hdrDiagnostic = "HDR output not attempted"
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
    // Reduce the neural network workload on sustained slow frames. The original
    // decoder image remains full resolution for chroma and the final composite.
    private var neuralScale = 1.0f
    private var slowFrames = 0
    private var fastFrames = 0
    private var presentedFrames = 0
    private var hasVideoFrame = false
    @Volatile private var diagnosticEnabled = false
    @Volatile private var vulkanBridge: VulkanHdrBridgeView? = null
    private var sharedFbo = 0
    private var sharedW = 0
    private var sharedH = 0
    private var hdrDiagnosticFrameCount = 0
    @Volatile private var decoderFrameCount = 0
    @Volatile private var glDrawCount = 0
    @Volatile private var hdrPresentAttempts = 0
    @Volatile private var hdrPresentSuccesses = 0
    @Volatile private var lastInteropError = "none"
    fun hdrSnapshot(): String = "Decoder frames=$decoderFrameCount, GL draws=$glDrawCount, " +
        "shared FBO=$sharedFbo ($sharedW x $sharedH), " +
        "HDR presents=$hdrPresentSuccesses/$hdrPresentAttempts, blue frames=$hdrDiagnosticFrameCount, " +
        "GL error=$lastInteropError; out=$outW x $outH"

    fun attachVulkan(bridge: VulkanHdrBridgeView?) {
        vulkanBridge = bridge
    }

    fun setDiagnostic(enabled: Boolean) {
        diagnosticEnabled = enabled
        requestRender()
    }
    private val vertices = ByteBuffer.allocateDirect(32).order(ByteOrder.nativeOrder()).asFloatBuffer()
        .apply { put(floatArrayOf(-1f,-1f, 1f,-1f, -1f,1f, 1f,1f)); position(0) }

    init {
        setEGLContextClientVersion(3)
        if (hdrRequested) {
            // Request true 10-bit EGL buffers, not an SDR framebuffer with
            // brightened colours. Only mark HDR active if PQ EGL creation works.
            // The Shield may expose no RGB10 EGLConfig at all. Asking
            // GLSurfaceView for a mandatory 10:10:10:2 config crashes its GL
            // thread with "No configs match configSpec". Pick the best supported
            // ES2/ES3-compatible window config and only attempt PQ on RGB10.
            setEGLConfigChooser(object : GLSurfaceView.EGLConfigChooser {
                override fun chooseConfig(egl: EGL10, display: EGLDisplay): EGLConfig {
                    val spec = intArrayOf(
                        0x3040, 4, // EGL_RENDERABLE_TYPE: EGL_OPENGL_ES2_BIT
                        0x3033, 4, // EGL_SURFACE_TYPE: EGL_WINDOW_BIT
                        EGL10.EGL_NONE
                    )
                    val count = IntArray(1)
                    check(egl.eglChooseConfig(display,spec,null,0,count) && count[0] > 0) {
                        "No GLES-compatible EGL window configs"
                    }
                    val configs = arrayOfNulls<EGLConfig>(count[0])
                    check(egl.eglChooseConfig(display,spec,configs,configs.size,count)) {
                        "Could not query EGL window configs"
                    }
                    fun channel(cfg: EGLConfig, attribute: Int): Int {
                        val value=IntArray(1)
                        return if (egl.eglGetConfigAttrib(display,cfg,attribute,value)) value[0] else 0
                    }
                    val candidates=configs.filterNotNull()
                    val rgb10=candidates.firstOrNull {
                        channel(it,EGL10.EGL_RED_SIZE)>=10 &&
                        channel(it,EGL10.EGL_GREEN_SIZE)>=10 &&
                        channel(it,EGL10.EGL_BLUE_SIZE)>=10
                    }
                    val rgb8=candidates.firstOrNull {
                        channel(it,EGL10.EGL_RED_SIZE)>=8 &&
                        channel(it,EGL10.EGL_GREEN_SIZE)>=8 &&
                        channel(it,EGL10.EGL_BLUE_SIZE)>=8
                    }
                    hdrConfigTenBit = rgb10 != null
                    hdrDiagnostic = "EGL RGB10 config: " + (rgb10 != null) + "; RGB8 config: " + (rgb8 != null)
                    return rgb10 ?: rgb8 ?: candidates.first()
                }
            })
            setEGLWindowSurfaceFactory(object : GLSurfaceView.EGLWindowSurfaceFactory {
                override fun createWindowSurface(
                    egl: EGL10, display: EGLDisplay, config: EGLConfig, nativeWindow: Any
                ): EGLSurface {
                    hdrSurfaceActive = false
                    val extensions = egl.eglQueryString(display,EGL10.EGL_EXTENSIONS).orEmpty()
                    val supportsPQ = extensions.contains("EGL_EXT_gl_colorspace_bt2020_pq")
                    hdrDiagnostic += "; EGL BT.2020 PQ extension: " + supportsPQ
                    // A 10-bit EGL window config is not a prerequisite for
                    // requesting BT.2020/PQ on all Android implementations.
                    // Android maps this colourscape to an HDR dataspace.
                    // Let EGL decide whether this exact window/config can use PQ.
                    if (extensions.contains("EGL_EXT_gl_colorspace_bt2020_pq")) {
                        val attrs = intArrayOf(0x309D,0x3340,EGL10.EGL_NONE)
                        val surface = egl.eglCreateWindowSurface(display,config,nativeWindow,attrs)
                        if (surface != null && surface != EGL10.EGL_NO_SURFACE) {
                            hdrSurfaceActive = true
                            hdrDiagnostic += "; PQ surface: CREATED"
                            Log.i("Reflite HDR10", "EGL BT2020 PQ window created; RGB10 config=" + hdrConfigTenBit)
                            return surface
                        }
                        val eglError = egl.eglGetError()
                        hdrDiagnostic += "; PQ create error: 0x" + Integer.toHexString(eglError)
                        Log.w("Reflite HDR10", "EGL rejected BT2020 PQ surface, error=" + eglError)
                    }
                    // Keep normal FSRCNNX image unaffected on unsupported drivers.
                    Log.w("Reflite HDR10", "PQ unavailable, using SDR window; extensions support PQ=" +
                        extensions.contains("EGL_EXT_gl_colorspace_bt2020_pq"))
                    return egl.eglCreateWindowSurface(display,config,nativeWindow,null)
                }
                override fun destroySurface(egl: EGL10, display: EGLDisplay, surface: EGLSurface) {
                    hdrSurfaceActive = false
                    egl.eglDestroySurface(display,surface)
                }
            })
        }
        setRenderer(this)
        renderMode = RENDERMODE_WHEN_DIRTY
        setZOrderMediaOverlay(true)
        holder.setFixedSize(3840,2160)
    }

    fun setSourceSize(w: Int, h: Int) {
        if (w !in 1..1920 || h !in 1..1080 || (w < 960 && h < 540)) return
        queueEvent { srcW = w; srcH = h; surfaceTexture?.setDefaultBufferSize(w,h); allocatedW = 0 }
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
            val trainedModel = context.assets.open("reflite/FSRCNNX_x2_8-0-4-1.glsl")
                .bufferedReader().use { it.readText() }
            neuralPipeline = FsrcnnxPipeline(trainedModel)
            if (hdrRequested && !hdrSurfaceActive) {
                val detail = hdrDiagnostic
                post { onHdrUnavailable?.invoke(detail) }
            }
            surfaceTexture = SurfaceTexture(texVideo).also { st ->
                st.setDefaultBufferSize(srcW, srcH)
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
            val newFrame = pending.getAndSet(false)
            if (newFrame) {
                surfaceTexture?.updateTexImage()
                surfaceTexture?.getTransformMatrix(transform)
                hasVideoFrame = true
                decoderFrameCount++
            }
            if (!hasVideoFrame) return
            glDrawCount++
            val workW = (srcW * neuralScale).toInt().coerceAtLeast(1)
            val workH = (srcH * neuralScale).toInt().coerceAtLeast(1)
            // Full GPU fences on every frame add CPU/GPU stalls and can cause
            // video to lag audio. Sample completion only every eighth new frame.
            val sampleGpu = newFrame && (++presentedFrames % 8 == 0)
            val start = if (sampleGpu) System.nanoTime() else 0L
            val bridge = vulkanBridge?.takeIf { it.isReady() }
            if (bridge != null && newFrame) {
                // True GPU-to-GPU path: FSRCNNX writes BT2020/PQ FP16 directly
                // to an EGLImage backed by an Android hardware buffer. Vulkan
                // imports the same allocation; no glReadPixels or CPU transfer.
                // Start conservatively at source size, preserving neural detail.
                val captureW = srcW.coerceAtLeast(2)
                val captureH = srcH.coerceAtLeast(2)
                if (sharedFbo == 0 || sharedW != captureW || sharedH != captureH) {
                    if (sharedFbo != 0) bridge.releaseSharedGL()
                    sharedFbo = bridge.prepareShared(captureW, captureH)
                    if (sharedFbo == 0) lastInteropError = "shared framebuffer allocation failed"
                    sharedW = captureW
                    sharedH = captureH
                }
                if (sharedFbo != 0) {
                    if (hdrDiagnosticFrameCount < 48) {
                        // Distinctive GPU-only HDR diagnostic for approximately
                        // the first 48 frames. If blue appears but movie stays
                        // black, Vulkan import/presentation works and the problem
                        // is in FSRCNNX composition. No CPU readback.
                        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, sharedFbo)
                        GLES30.glViewport(0, 0, captureW, captureH)
                        GLES30.glClearColor(0.13f, 0.42f, 0.67f, 1.0f)
                        GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT)
                        hdrDiagnosticFrameCount++
                    } else {
                        neuralPipeline?.render(texVideo, transform, workW, workH,
                            captureW, captureH, false, true, sharedFbo)
                    }
                    GLES30.glFinish()
                    val glError = GLES30.glGetError()
                    if (glError != GLES30.GL_NO_ERROR)
                        lastInteropError = "GLES error 0x" + glError.toString(16)
                    hdrPresentAttempts++
                    if (bridge.presentShared()) hdrPresentSuccesses++
                }
            } else {
                neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                    diagnosticEnabled, hdrRequested && hdrSurfaceActive)
            }
            if (sampleGpu) {
                GLES30.glFinish()
                val elapsedMs = (System.nanoTime() - start) / 1_000_000.0
                // Start at native source size. If rendering repeatedly misses a
                // 30fps budget, progressively back off: 1080p -> ~810p -> 540p.
                if (elapsedMs > 29.0) { slowFrames++; fastFrames = 0 }
                else if (elapsedMs < 13.0) { fastFrames++; slowFrames = 0 }
                else { slowFrames = 0; fastFrames = 0 }
                if (slowFrames >= 2 && neuralScale > 0.51f) {
                    neuralScale = if (neuralScale > 0.9f) 0.75f else 0.5f
                    slowFrames = 0
                    Log.i("Reflite GPU", "FSRCNNX performance scale -> " + neuralScale)
                }
                // Avoid oscillation: recover quality only after prolonged headroom.
                if (fastFrames >= 30 && neuralScale < 1.0f) {
                    neuralScale = if (neuralScale < 0.6f) 0.75f else 1.0f
                    fastFrames = 0
                }
            }
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
            neuralPipeline?.close()
            neuralPipeline=null
            if (texIntermediate!=0) GLES30.glDeleteTextures(1,intArrayOf(texIntermediate),0)
            if (framebuffer!=0) GLES30.glDeleteFramebuffers(1,intArrayOf(framebuffer),0)
            texIntermediate=0
            framebuffer=0
            if (sharedFbo != 0) vulkanBridge?.releaseSharedGL()
            sharedFbo = 0
            sharedW = 0
            sharedH = 0
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
            // 8-tap Blackman-windowed sinc; adaptive damping at strong edges.
            float kernel(float x, float cutoff) {
                float a=abs(x);
                if(a>=4.0) return 0.0;
                float p=PI*cutoff*x;
                float sinc=abs(p)<0.00001?1.0:sin(p)/p;
                float w=0.42+0.5*cos(PI*a/4.0)+0.08*cos(2.0*PI*a/4.0);
                return cutoff*sinc*w;
            }
            float edgeStrength(vec3 l,vec3 c,vec3 r) {
                vec3 grad=abs(l-r);
                vec3 curvature=abs(l-2.0*c+r);
                return clamp(dot(grad+curvature,vec3(0.2126,0.7152,0.0722))*1.5,0.0,1.0);
            }
        """
        private val shaderHorizontal="""#version 300 es
            #extension GL_OES_EGL_image_external_essl3 : require
            precision highp float;
            uniform samplerExternalOES video;
            uniform mat4 texMatrix;
            uniform vec2 inputSize;
            in vec2 uv; out vec4 colorOut;
            // Original Reflite Neural 2x, 8 hidden features, 3x3 convolution,
            // ReLU and four learned subpixel luminance residuals.
            const float W[72]=float[72](0.0596994,0.0086669,-0.0134230,0.0103808,0.2477307,-0.0295387,0.0965691,-0.0108631,0.1339298,-0.0976552,0.1159188,0.0110902,-0.1309186,-0.2134059,-0.0390848,-0.1141308,0.1323335,0.1644483,0.0631525,-0.0143496,-0.0448847,-0.0397466,0.1370724,0.0739098,-0.0214029,0.0738234,-0.0479896,0.0811354,0.0725350,0.1013255,-0.0790461,-0.1462412,0.0753565,-0.0328518,-0.0449193,0.0289933,0.1028217,0.0097367,-0.1132892,0.1118558,-0.2434822,0.0250340,0.0060627,0.1308180,0.0319086,-0.0516564,-0.0435863,0.0415384,0.0980680,-0.2619476,0.1004270,-0.0296154,0.1207969,0.0105051,0.0508897,0.0863300,0.0059038,-0.0782966,-0.1881388,-0.0115275,0.1349362,-0.0504053,0.1251914,0.0421386,0.0047298,0.0001191,0.0532849,-0.2920664,0.0335856,0.2020138,0.0046284,-0.0337481);
            const float B[8]=float[8](-0.0165405,-0.0000500,-0.0210086,0.0058868,0.0305399,-0.0095345,-0.0092669,-0.0190037);
            const float M[32]=float[32](0.1072826,-0.0725972,-0.0297296,-0.3055864,-0.3001271,-0.3100334,-0.1282784,-0.4923159,0.1025373,-0.0638999,0.0519550,-0.4212372,-0.2393530,-0.8458929,-0.2125198,0.0776311,0.0792031,-0.1713681,0.0205096,-0.0906425,-0.2985714,-0.4134095,-0.2273034,-0.6127194,0.0855680,-0.1462402,0.0686520,-0.2102010,-0.2210968,-0.9513974,-0.3159298,-0.0201317);
            const float O[4]=float[4](0.0103235,0.0104369,0.0091512,0.0084687);
            vec3 fetchRGB(vec2 pos) {
                vec2 st=(pos+vec2(0.5))/inputSize;
                return texture(video,(texMatrix*vec4(st,0.0,1.0)).xy).rgb;
            }
            void main() {
                vec2 srcPixel=floor(gl_FragCoord.xy*0.5);
                float patch[9];
                for(int j=0;j<3;j++){
                    for(int i=0;i<3;i++){
                        vec3 rgb=fetchRGB(srcPixel+vec2(float(i-1),float(j-1)));
                        patch[j*3+i]=dot(rgb,vec3(0.2126,0.7152,0.0722));
                    }
                }
                float hidden[8];
                for(int h=0;h<8;h++){
                    float val=B[h];
                    for(int k=0;k<9;k++) val+=W[h*9+k]*patch[k];
                    hidden[h]=max(0.0,val);
                }
                int sx=int(mod(floor(gl_FragCoord.x-0.5),2.0));
                int sy=int(mod(floor(gl_FragCoord.y-0.5),2.0));
                int channel=sy*2+sx;
                float residual=O[channel];
                for(int h=0;h<8;h++) residual+=M[channel*8+h]*hidden[h];
                // Spatial luma residual; retain source chroma and original grain.
                vec3 base=texture(video,(texMatrix*vec4(uv,0.0,1.0)).xy).rgb;
                float limited=clamp(residual,-0.12,0.12);
                colorOut=vec4(clamp(base+vec3(limited),0.0,1.0),1.0);
            }
        """
        private val shaderVertical="""#version 300 es
            precision highp float;
            uniform sampler2D video;
            uniform float diagnostic;
            in vec2 uv; out vec4 colorOut;
            void main() {
                colorOut=texture(video,uv);
                if(diagnostic>0.5 && uv.x<0.20 && uv.y>0.91)
                    colorOut=vec4(1.0,0.0,1.0,1.0);
            }
        """
    }
}
