from pathlib import Path
import shutil
root=Path("proj/app/src/main/java/com/example/liteplayer")
shutil.copyfile("research/fsrcnnx/Temporal1080.kt",root/"Temporal1080.kt")
p=root/"ReferenceScalerView.kt"
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)
once("    private var temporal720Announced = false","    private var temporal720Announced = false\n    private var temporal1080: Temporal1080? = null\n    private var temporal1080Failed = false\n    private var temporal1080Announced = false")
once("            temporal720Announced = false","            temporal720Announced = false\n            temporal1080 = null\n            temporal1080Failed = false\n            temporal1080Announced = false")
once("""            if (!temporalRendered) {
                selected?.render""","""            if (srcW == 1920 && srcH == 1080 && !diagnosticEnabled && !temporal1080Failed) {
                try {
                    val temporal = temporal1080 ?: Temporal1080().also { temporal1080 = it }
                    temporal.render(texVideo, transform, outW, outH,
                        surfaceTexture?.timestamp ?: 0L, newFrame)
                    temporalRendered = true
                    if (!temporal1080Announced) {
                        temporal1080Announced = true
                        post { android.widget.Toast.makeText(context, "Temporal 1080p Cinema active", android.widget.Toast.LENGTH_SHORT).show() }
                    }
                } catch (error: Throwable) {
                    temporal1080Failed = true
                    post { android.widget.Toast.makeText(context, "Temporal 1080p unavailable: FSRCNNX fallback", android.widget.Toast.LENGTH_LONG).show() }
                    temporal1080?.close()
                    temporal1080 = null
                    GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
                    repeat(16) { if (GLES30.glGetError() == GLES30.GL_NO_ERROR) return@repeat }
                }
            } else {
                temporal1080?.invalidate()
            }
            if (!temporalRendered) {
                selected?.render""")
once("            temporal720?.close()\n            temporal720 = null\n            neural16Pipeline?.close()","            temporal720?.close()\n            temporal720 = null\n            temporal1080?.close()\n            temporal1080 = null\n            neural16Pipeline?.close()")
p.write_text(s)
print("Independent 1080p temporal path; 720p renderer and original synchronization unchanged.")
