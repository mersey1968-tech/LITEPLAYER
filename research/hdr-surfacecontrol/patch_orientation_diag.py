"""Reflite-only fix: OpenGL framebuffer origin vs SurfaceControl consumer,
plus a one-shot diagnostic of 10-bit buffer submissions. No LitePlayer changes.
Executed after patch_surfacecontrol.py in the assembled test project.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
def replace_unique(src,a,b,label):
    n=src.count(a)
    if n!=1: raise RuntimeError(f"{label}: expected one occurrence, got {n}")
    return src.replace(a,b,1)

# Composite is the *final* operation after all 14 pretrained network stages.
# Only swap source-sampling V coordinates when drawing into the native
# AHardwareBuffer, because it uses the opposite origin from the EGL window.
# SDR mode, model input and model output remain bit-for-bit as before.
s=replace_unique(s,
    '''                float y=texture(uNeural,uv).r;
                vec3 rgb=texture(uVideo,(uMatrix*vec4(uv,0.,1.)).xy).rgb;''',
    '''                vec2 outputUv=(uHdr>0.5)?vec2(uv.x,1.0-uv.y):uv;
                float y=texture(uNeural,outputUv).r;
                vec3 rgb=texture(uVideo,(uMatrix*vec4(outputUv,0.,1.)).xy).rgb;''',
    "FSRCNNX final composite orientation")
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
s=replace_unique(s,
    '    private var nativeHdrFailureShown = false',
    '''    private var nativeHdrFailureShown = false
    private var nativeHdrPresentedFrames = 0
    private var nativeHdrReportSent = false
    var onHdrDiagnostic: ((String) -> Unit)? = null''',
    "HDR debug fields")
s=replace_unique(s,
    '''                if (!HdrSurfaceControl.present(nativeHdrLayer)) {
                    fail("SurfaceControl HDR buffer presentation failed: " +
                        HdrSurfaceControl.lastError())
                    return
                }''',
    '''                if (!HdrSurfaceControl.present(nativeHdrLayer)) {
                    fail("SurfaceControl HDR buffer presentation failed: " +
                        HdrSurfaceControl.lastError())
                    return
                }
                nativeHdrPresentedFrames++
                if (!nativeHdrReportSent && nativeHdrPresentedFrames >= 48) {
                    nativeHdrReportSent = true
                    val status = HdrSurfaceControl.snapshot(nativeHdrLayer)
                    post { onHdrDiagnostic?.invoke(status) }
                }''',
    "HDR submission report")
s=replace_unique(s,
    '''        nativeHdrAttempted = false
        outW = w''',
    '''        nativeHdrAttempted = false
        nativeHdrPresentedFrames = 0
        nativeHdrReportSent = false
        outW = w''',
    "HDR resize counters")
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
s=replace_unique(s,
    '''            gpu.onHdrUnavailable = { details ->''',
    '''            gpu.onHdrDiagnostic = { details ->
                if (scalerView === gpu && referenceHdrEnabled && !isFinishing) {
                    AlertDialog.Builder(this)
                        .setTitle("Reflite HDR10 compositor diagnostic")
                        .setMessage(details + "\\n\\nA successful buffer submission does not establish HDMI HDR output. Verify the Bravia 9 HDR indicator.")
                        .setPositiveButton("OK", null).show()
                }
            }
            gpu.onHdrUnavailable = { details ->''',
    "HDR one-shot dialog")
p.write_text(s)
print("Corrected native HDR framebuffer vertical orientation and added 48-frame compositor diagnostic")
