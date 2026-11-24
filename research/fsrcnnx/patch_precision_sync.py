"""Reflite precision sync: preserve shaders and texture semantics."""
from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1, (a,s.count(a))
    return s.replace(a,b,1)
p=root/"FsrcnnxPipeline.kt"
s=p.read_text()
# Keep the final linear-filtered texture separate from nearest-filtered features.
s=once(s,"val existing=free.indexOfFirst { it.w==tw && it.h==th }","val existing=if (idx == stages.lastIndex) -1 else free.indexOfFirst { it.w==tw && it.h==th }")
p.write_text(s)
p=root/"ReferenceScalerView.kt"
s=p.read_text()
# Do not compile the expensive 16-channel model for 1080p at startup.
s=once(s,"if (neural16Pipeline == null && !neural16Unavailable) {","if (srcH <= 800 && neural16Pipeline == null && !neural16Unavailable) {") if s.count("if (neural16Pipeline == null && !neural16Unavailable) {")==1 else s
# Avoid a synchronous GPU drain for periodic timing; do not change adaptive resolution
# behavior in this test, since its existing threshold depends on completed GPU time.
s=once(s,"    var onSurfaceReady: ((Surface) -> Unit)? = null","    var onSurfaceReady: ((Surface) -> Unit)? = null\n    var onFirstNeuralFrame: (() -> Unit)? = null\n    private var firstNeuralFrameReported = false")
s=once(s,"            failed = false","            failed = false\n            firstNeuralFrameReported = false")
a="            if (sampleGpu) {"
s=once(s,a,"            if (newFrame && !firstNeuralFrameReported) {\n                firstNeuralFrameReported = true\n                // Submitted on the GL thread; callback is not a display-present guarantee.\n                post { onFirstNeuralFrame?.invoke() }\n            }\n"+a)
p.write_text(s)
p=root/"MainActivity.kt"
s=p.read_text()
a='''                    if (resume1080AfterSurface) {
                        activePlayer.playWhenReady = true
                        android.util.Log.i("Reflite Startup",
                            "1080p: neural decoder Surface attached; resume playback")
                    }'''
b='''                    if (resume1080AfterSurface) {
                        // A paused Media3 renderer can submit its initial video frame.
                        // Bounded fallback prevents a deadlock on decoder implementations
                        // that need active playback to produce the first frame.
                        var waitingForNeuralFrame = true
                        val resume = {
                            if (waitingForNeuralFrame) {
                                waitingForNeuralFrame = false
                                if (player === activePlayer && scalerView === gpu &&
                                    referenceScalerEnabled && !isFinishing) {
                                    activePlayer.playWhenReady = true
                                }
                            }
                        }
                        gpu.onFirstNeuralFrame = { resume() }
                        android.os.Handler(android.os.Looper.getMainLooper())
                            .postDelayed({ resume() }, 800L)
                    }'''
s=once(s,a,b)
a='''                Toast.makeText(this, "GPU overlay unavailable", Toast.LENGTH_LONG).show()'''
s=once(s,a,'''                if (resume1080AfterSurface && player === activePlayer) {
                    activePlayer.playWhenReady = true
                }
'''+a)
p.write_text(s)
print("Precision Sync: distinct final filter target, bounded first-frame handoff, unchanged shaders.")
