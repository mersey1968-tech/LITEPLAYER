"""Opt-in non-Vulkan Reflite SDR -> FSRCNNX -> BT2020/PQ experiment.
Runs only after the known-good subtitle-fixed Reflite staging scripts.
Never changes LitePlayer branches or the working SDR APK.
"""
from pathlib import Path

main = Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=main.read_text()
def once(old,new):
    global s
    count=s.count(old)
    if count!=1: raise RuntimeError(f"Expected one MainActivity match; found {count}: {old[:110]!r}")
    s=s.replace(old,new,1)

once(
    '            "FSRCNNX Neural (SDR)"',
    '            "FSRCNNX Neural (SDR)",\n            "FSRCNNX Neural + HDR10 (native experimental)"'
)
once('if (referenceScalerEnabled) 1 else 0',
     'if (!referenceScalerEnabled) 0 else if (referenceHdrEnabled) 2 else 1')
once(
    '''                referenceScalerEnabled = which == 1
                getSharedPreferences("reflite_video", MODE_PRIVATE).edit()
                    .putBoolean("neural_enabled", referenceScalerEnabled).apply()
''',
    '''                val wantHdr = which == 2
                // Recreate the EGL surface when transitioning HDR <-> SDR.
                // Keep the working SDR view independent from the HDR experiment.
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
    '''        val renderPrefs = getSharedPreferences("reflite_video", MODE_PRIVATE)
        val savedMode = renderPrefs.getInt("render_mode",
            if (renderPrefs.getBoolean("neural_enabled", false)) 1 else 0).coerceIn(0, 2)
        referenceHdrEnabled = savedMode == 2
        referenceScalerEnabled = savedMode != 0
        findViewById<Button>(R.id.refliteScalerButton)'''
)
once(
    '''        referenceScalerEnabled = getSharedPreferences("reflite_video", MODE_PRIVATE)
            .getBoolean("neural_enabled", false)
        currentVideoFormat = null''',
    '''        val resumedPrefs = getSharedPreferences("reflite_video", MODE_PRIVATE)
        val resumedMode = resumedPrefs.getInt("render_mode",
            if (resumedPrefs.getBoolean("neural_enabled", false)) 1 else 0).coerceIn(0, 2)
        referenceHdrEnabled = resumedMode == 2
        referenceScalerEnabled = resumedMode != 0
        currentVideoFormat = null'''
)
# Restore previous user selection if a particular unsupported format temporarily
# disables the scaler. Only explicit menu choices write the preference.
main.write_text(s)

renderer = Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
r=renderer.read_text()
old='import android.view.Surface\n'
assert r.count(old)==1
r=r.replace(old,old+'import android.view.SurfaceHolder\n',1)
old='''                    return egl.eglCreateWindowSurface(display,config,nativeWindow,null)'''
new='''                    val normal = egl.eglCreateWindowSurface(display,config,nativeWindow,null)
                    // Unlike the failed EGL_BT2020_PQ window creation, request
                    // BT.2020/PQ directly on the BufferQueue (API 28+) after EGL
                    // creates a conventional window. Actual HDMI HDR is device
                    // dependent and must be verified on the TV.
                    val surface = when(nativeWindow) {
                        is Surface -> nativeWindow
                        is SurfaceHolder -> nativeWindow.surface
                        else -> null
                    }
                    if (normal != null && normal != EGL10.EGL_NO_SURFACE && surface != null) {
                        val nativeResult = runCatching {
                            HdrNativeDataspace.setHdr(surface)
                        }.getOrElse {
                            hdrDiagnostic += "; native exception=" + it.message
                            -200
                        }
                        hdrSurfaceActive = nativeResult == 1
                        hdrDiagnostic += "; NDK buffer BT2020/PQ result=" + nativeResult +
                            "; RGB10=" + hdrConfigTenBit
                        Log.i("Reflite HDR10", hdrDiagnostic)
                    }
                    return normal'''
assert r.count(old)==1
r=r.replace(old,new,1)
old='''            neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false)'''
new='''            neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, hdrRequested && hdrSurfaceActive)'''
assert r.count(old)==1
r=r.replace(old,new,1)
renderer.write_text(r)
print("Reflite native HDR experiment applied; ordinary SDR neural path unchanged")
