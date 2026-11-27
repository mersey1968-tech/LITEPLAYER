from pathlib import Path
import shutil
root=Path("proj/app/src/main/java/com/example/liteplayer")
shutil.copyfile("research/fsrcnnx/Temporal720.kt",root/"Temporal720.kt")
p=root/"ReferenceScalerView.kt"
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)
once("    private var neuralScale = 1.0f","    private var neuralScale = 1.0f\n    private var temporal720: Temporal720? = null\n    private var temporal720Failed = false\n    private var temporal720Announced = false")
# New context invalidates old texture names; old context owns its allocations.
once("            failed = false","            failed = false\n            temporal720 = null\n            temporal720Failed = false\n            temporal720Announced = false")
a="""            selected?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false, originalFrameHeight=srcH, reuseInference=!newFrame)"""
b="""            var temporalRendered = false
            if (srcW == 1280 && srcH == 720 && !diagnosticEnabled && !temporal720Failed) {
                try {
                    val temporal = temporal720 ?: Temporal720().also { temporal720 = it }
                    temporal.render(texVideo, transform, outW, outH,
                        surfaceTexture?.timestamp ?: 0L, newFrame)
                    temporalRendered = true
                    if (!temporal720Announced) {
                        temporal720Announced = true
                        post { android.widget.Toast.makeText(context, "Temporal 720p active", android.widget.Toast.LENGTH_SHORT).show() }
                    }
                } catch (error: Throwable) {
                    temporal720Failed = true
                    post { android.widget.Toast.makeText(context, "Temporal unavailable: FSRCNNX fallback", android.widget.Toast.LENGTH_LONG).show() }
                    temporal720?.close()
                    temporal720 = null
                    GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
                    while (GLES30.glGetError() != GLES30.GL_NO_ERROR) { }
                }
            } else {
                temporal720?.invalidate()
            }
            if (!temporalRendered) {
                selected?.render(texVideo, transform, workW, workH, outW, outH,
                    diagnosticEnabled, false, originalFrameHeight=srcH, reuseInference=!newFrame)
            }"""
once(a,b)
once("            neural16Pipeline?.close()","            temporal720?.close()\n            temporal720 = null\n            neural16Pipeline?.close()")
p.write_text(s)
print("Temporal 720p renderer attached with baseline fallback; original audio clock and synchronization retained.")
