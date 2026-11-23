"""Append a native SurfaceControl HDR10 path to the isolated Reflite build.
Apply after the stable SDR cleanup and successful dedicated subtitle overlay.
The original LitePlayer and the known-good Reflite branch are never modified.
"""
from pathlib import Path

main=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=main.read_text()
def once(old,new):
    global s
    n=s.count(old)
    if n!=1: raise RuntimeError(f"MainActivity: expected 1 match, got {n}: {old[:90]!r}")
    s=s.replace(old,new,1)

once(
    '            "FSRCNNX Neural (SDR)"',
    '            "FSRCNNX Neural (SDR)",\n            "FSRCNNX Neural + HDR10 (SurfaceControl test)"'
)
once('if (referenceScalerEnabled) 1 else 0',
    'if (!referenceScalerEnabled) 0 else if (referenceHdrEnabled) 2 else 1')
once(
    '''                referenceScalerEnabled = which == 1
                getSharedPreferences("reflite_video", MODE_PRIVATE).edit()
                    .putBoolean("neural_enabled", referenceScalerEnabled).apply()
''',
    '''                val wantHdr = which == 2
                if (scalerView != null && referenceHdrEnabled != wantHdr) {
                    referenceScalerEnabled = false
                    applyRefliteScaler()
                }
                referenceHdrEnabled = wantHdr
                referenceScalerEnabled = which != 0
                getSharedPreferences("reflite_video", MODE_PRIVATE).edit()
                    .putInt("render_mode", which)
                    .putBoolean("neural_enabled", referenceScalerEnabled).apply()
'''
)
once('            val gpu = ReferenceScalerView(this, false)',
     '            val gpu = ReferenceScalerView(this, referenceHdrEnabled)')
once(
    '''        referenceScalerEnabled = getSharedPreferences("reflite_video", MODE_PRIVATE)
            .getBoolean("neural_enabled", false)
        findViewById<Button>(R.id.refliteScalerButton)''',
    '''        val prefsReflite = getSharedPreferences("reflite_video", MODE_PRIVATE)
        val savedMode = prefsReflite.getInt("render_mode",
            if (prefsReflite.getBoolean("neural_enabled", false)) 1 else 0).coerceIn(0, 2)
        referenceHdrEnabled = savedMode == 2
        referenceScalerEnabled = savedMode != 0
        findViewById<Button>(R.id.refliteScalerButton)'''
)
once(
    '''        referenceScalerEnabled = getSharedPreferences("reflite_video", MODE_PRIVATE)
            .getBoolean("neural_enabled", false)
        currentVideoFormat = null''',
    '''        val resumePrefs = getSharedPreferences("reflite_video", MODE_PRIVATE)
        val resumeMode = resumePrefs.getInt("render_mode",
            if (resumePrefs.getBoolean("neural_enabled", false)) 1 else 0).coerceIn(0, 2)
        referenceHdrEnabled = resumeMode == 2
        referenceScalerEnabled = resumeMode != 0
        currentVideoFormat = null'''
)
# On an experimental output failure, select SDR without entering the same
# HDR path again until the user explicitly re-selects it. Avoid black frames.
once(
    '''            gpu.onHdrUnavailable = { details ->
                val displayHdr''',
    '''            gpu.onHdrUnavailable = { details ->
                referenceHdrEnabled = false
                referenceScalerEnabled = true
                getSharedPreferences("reflite_video", MODE_PRIVATE).edit()
                    .putInt("render_mode", 1).putBoolean("neural_enabled", true).apply()
                val displayHdr'''
)
main.write_text(s)

render=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
r=render.read_text()
def rr(old,new):
    global r
    n=r.count(old)
    if n!=1: raise RuntimeError(f"ReferenceScalerView: expected 1 match, got {n}: {old[:80]!r}")
    r=r.replace(old,new,1)

rr(
    '    @Volatile private var hdrSurfaceActive = false',
    '''    @Volatile private var hdrSurfaceActive = false
    private var nativeHdrLayer: Long = 0L
    private var nativeHdrAttempted = false
    private var nativeHdrFailureShown = false
    private fun releaseHdrLayer() {
        val old = nativeHdrLayer
        nativeHdrLayer = 0L
        if (old != 0L) HdrSurfaceControl.destroy(old)
        hdrSurfaceActive = false
    }'''
)
# Remove the failed EGL_BT2020_PQ path entirely. EGL 8-bit view stays an
# ordinary SDR-compatible window and can host a 10-bit native child surface.
start=r.index('        if (hdrRequested) {\n            // Request true 10-bit EGL buffers')
end=r.index('        setRenderer(this)',start)
r=r[:start]+r[end:]
rr(
    '''            if (hdrRequested && !hdrSurfaceActive) {
                val detail = hdrDiagnostic
                post { onHdrUnavailable?.invoke(detail) }
            }
''',''
)
rr(
    '''    override fun onSurfaceChanged(gl: GL10?, w: Int, h: Int) {
        outW = w
        outH = h
    }''',
    '''    override fun onSurfaceChanged(gl: GL10?, w: Int, h: Int) {
        if (nativeHdrLayer != 0L) releaseHdrLayer()
        nativeHdrAttempted = false
        outW = w
        outH = h
    }'''
)
rr(
    '''            neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false)''',
    '''            if (hdrRequested && !nativeHdrAttempted) {
                nativeHdrAttempted = true
                // Import the 10-bit hardware-buffer images into this existing
                // FSRCNNX OpenGL context, not into another GPU API.
                nativeHdrLayer = runCatching {
                    HdrSurfaceControl.create(holder.surface, outW, outH)
                }.getOrElse { ex ->
                    hdrDiagnostic = "SurfaceControl initialization exception: " + ex.message
                    0L
                }
                hdrSurfaceActive = nativeHdrLayer != 0L
                if (!hdrSurfaceActive && !nativeHdrFailureShown) {
                    nativeHdrFailureShown = true
                    if (hdrDiagnostic.isEmpty() || hdrDiagnostic=="HDR output not attempted")
                        hdrDiagnostic = runCatching { HdrSurfaceControl.lastError() }
                            .getOrDefault("Unknown 10-bit SurfaceControl failure")
                    val message = hdrDiagnostic
                    post { onHdrUnavailable?.invoke("SurfaceControl: " + message) }
                }
            }
            var renderToHdr = false
            val targetFbo = if (nativeHdrLayer != 0L) {
                val target = HdrSurfaceControl.begin(nativeHdrLayer)
                if (target > 0) renderToHdr = true
                target
            } else 0
            if (renderToHdr) {
                neuralPipeline?.render(texVideo, transform, workW, workH,
                    outW, outH, diagnosticEnabled, true, targetFbo)
                if (!HdrSurfaceControl.present(nativeHdrLayer)) {
                    fail("SurfaceControl HDR buffer presentation failed: " +
                        HdrSurfaceControl.lastError())
                    return
                }
            } else if (nativeHdrLayer == 0L) {
                // Safe fallback; the BT2020/PQ transform is only applied when
                // rendering to an actual 10-bit HDR buffer.
                neuralPipeline?.render(texVideo, transform, workW, workH,
                    outW, outH, diagnosticEnabled, false)
            }
            // If the 3 buffers are still occupied by the compositor, skip a
            // frame rather than overwrite a buffer or block decoder audio.'''
)
rr(
    '''    fun close() {
        onSurfaceReady=null''',
    '''    fun close() {
        onSurfaceReady=null'''
)
rr(
    '''        queueEvent {
            surfaceTexture?.setOnFrameAvailableListener(null)''',
    '''        queueEvent {
            releaseHdrLayer()
            surfaceTexture?.setOnFrameAvailableListener(null)'''
)
render.write_text(r)
print("Reflite: integrated non-Vulkan SurfaceControl 10-bit HDR output + preserved working SDR/subtitle fallback")
