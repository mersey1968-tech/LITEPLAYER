"""Keep one decoder surface for eligible SDR playback.
Toggle only the GL drawing path; retain the exact existing neural shaders.
Direct hardware playback stays in place for HDR/DV and unsupported formats.
"""
from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
p=root/"MainActivity.kt"
s=p.read_text()
s=once(s,"    private var referenceScalerEnabled = false","""    private var referenceScalerEnabled = false
    private var sharedSdrSurfaceFailed = false
    private var releasingSharedSdrSurface = false""")
s=once(s,"if (!referenceScalerEnabled || !allowedForReferenceScaler(resolvedScalerFormat()) || activePlayer == null)","if (releasingSharedSdrSurface || sharedSdrSurfaceFailed || !allowedForReferenceScaler(resolvedScalerFormat()) || activePlayer == null)")
s=once(s,"                existing.setDiagnostic(referenceDiagnosticEnabled)","""                existing.setDiagnostic(referenceDiagnosticEnabled)
                existing.setNeuralMode(referenceScalerEnabled)""")
s=once(s,"            val gpu = ReferenceScalerView(this, false)","""            val gpu = ReferenceScalerView(this, false)
            gpu.setNeuralMode(referenceScalerEnabled)""")
s=once(s,"""                    referenceScalerEnabled = false
                    applyRefliteScaler()
                    if (resume1080AfterSurface""","""                    sharedSdrSurfaceFailed = true
                    referenceScalerEnabled = false
                    applyRefliteScaler()
                    if (resume1080AfterSurface""")
s=once(s,"if (referenceScalerEnabled && scalerView === gpu && player === activePlayer)","if (!sharedSdrSurfaceFailed && !releasingSharedSdrSurface && scalerView === gpu && player === activePlayer && allowedForReferenceScaler(resolvedScalerFormat()))")
s=once(s,"                                    referenceScalerEnabled && !isFinishing)","                                    !sharedSdrSurfaceFailed && !releasingSharedSdrSurface && !isFinishing)")
s=once(s,"""                referenceScalerEnabled = false
                scalerView = null""","""                sharedSdrSurfaceFailed = true
                referenceScalerEnabled = false
                scalerView = null""")
s=once(s,"""        referenceScalerEnabled = false
        applyRefliteScaler()
        referenceScalerEnabled = getSharedPreferences""","""        releasingSharedSdrSurface = true
        referenceScalerEnabled = false
        applyRefliteScaler()
        releasingSharedSdrSurface = false
        sharedSdrSurfaceFailed = false
        referenceScalerEnabled = getSharedPreferences""")
s=once(s,'"Original (no upscaling)"','"Original (GPU bypass)"')
p.write_text(s)
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=once(s,"    private var firstNeuralFrameReported = false","""    private var firstNeuralFrameReported = false
    @Volatile private var neuralMode = false
    private var bypassProgram = 0

    fun setNeuralMode(enabled: Boolean) {
        if (neuralMode == enabled) return
        neuralMode = enabled
        requestRender()
    }""")
s=once(s,"            neuralPipeline = FsrcnnxPipeline(trainedModel)","""            neuralPipeline = FsrcnnxPipeline(trainedModel)
            bypassProgram = link(shaderVertex, bypassFragment)""")
s=once(s,"            if (!hasVideoFrame) return","""            if (!hasVideoFrame) return
            // Original and Neural share the same OES texture and decoder surface.
            // Bypass does no neural inference or detail/color enhancement.
            if (!neuralMode) {
                GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
                GLES30.glViewport(0, 0, outW, outH)
                GLES30.glClearColor(0f, 0f, 0f, 1f)
                GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT)
                val aspect = srcW.toFloat() / srcH.coerceAtLeast(1)
                val fitW = minOf(outW, (outH * aspect).toInt()).coerceAtLeast(1)
                val fitH = minOf(outH, (outW / aspect).toInt()).coerceAtLeast(1)
                GLES30.glViewport((outW-fitW)/2, (outH-fitH)/2, fitW, fitH)
                pass(bypassProgram, texVideo, GLES11Ext.GL_TEXTURE_EXTERNAL_OES, srcW, srcH, transform)
                if (newFrame && !firstNeuralFrameReported) {
                    firstNeuralFrameReported = true
                    post { onFirstNeuralFrame?.invoke() }
                }
                return
            }""")
s=once(s,"            neuralPipeline=null","""            neuralPipeline=null
            if (bypassProgram != 0) GLES30.glDeleteProgram(bypassProgram)
            bypassProgram = 0""")
s=once(s,"    companion object {","""    companion object {
        private val bypassFragment = \"\"\"#version 300 es
            #extension GL_OES_EGL_image_external_essl3 : require
            precision highp float;
            uniform samplerExternalOES video;
            uniform mat4 texMatrix;
            in vec2 uv; out vec4 colorOut;
            void main() {
                colorOut = texture(video, (texMatrix * vec4(uv, 0.0, 1.0)).xy);
            }
        \"\"\"""")
# Python triple quotes above are escaped in the source; output must contain Kotlin triple quotes.
p.write_text(s)
print("Shared SDR decoder surface: Original bypass and Neural switch without seek or surface replacement.")
