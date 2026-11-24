"""Isolated Reflite Smooth Start experiment.

Based exclusively on the previously smooth 16-channel build. Reduce startup
synchronization overhead (avoid glFinish on initial 24 decoded frames), prevent
unnecessary re-inference for redraws without new decoded video, and log
timestamps and frame timing to diagnose any remaining startup hesitation.
The established full-resolution 16-channel network, richer blacks, scaling
fallback and Media3 audio/frame-rate pipeline remain untouched.
"""
from pathlib import Path

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()

a='''    private var presentedFrames = 0
    private var hasVideoFrame = false'''
b='''    private var presentedFrames = 0
    private var hasVideoFrame = false
    private var startupNs = 0L
    private var lastDecodedFrameNs = 0L
    private var firstRenderedFrameNs = 0L
    private var measuredStartupFrames = 0'''
assert s.count(a)==1, "startup fields anchor missing"
s=s.replace(a,b,1)

a='''            if (newFrame) {
                surfaceTexture?.updateTexImage()
                surfaceTexture?.getTransformMatrix(transform)
                hasVideoFrame = true

            }
            if (!hasVideoFrame) return

            val workW = (srcW * neuralScale).toInt().coerceAtLeast(1)'''
b='''            if (newFrame) {
                val now = System.nanoTime()
                if (startupNs == 0L) {
                    startupNs = now
                    Log.i("Reflite SmoothStart",
                        "First decoder frame: " + srcW + "x" + srcH)
                }
                val deltaMs = if (lastDecodedFrameNs != 0L)
                    (now-lastDecodedFrameNs)/1_000_000L else 0L
                lastDecodedFrameNs = now
                if (measuredStartupFrames < 64 &&
                    (measuredStartupFrames < 6 ||
                     measuredStartupFrames == 15 ||
                     measuredStartupFrames == 31 ||
                     measuredStartupFrames == 63)) {
                    Log.i("Reflite SmoothStart",
                        "Decoded frame " + (measuredStartupFrames+1) +
                        ", intervalMs=" + deltaMs +
                        ", elapsedMs=" + ((now-startupNs)/1_000_000L) +
                        ", neuralScale=" + neuralScale)
                }
                measuredStartupFrames++
                surfaceTexture?.updateTexImage()
                surfaceTexture?.getTransformMatrix(transform)
                hasVideoFrame = true

            }
            if (!hasVideoFrame) return
            // Avoid re-running neural inference on an unchanged video image.
            if (!newFrame && measuredStartupFrames > 0) return

            val workW = (srcW * neuralScale).toInt().coerceAtLeast(1)'''
assert s.count(a)==1, "frame receipt anchor missing"
s=s.replace(a,b,1)
a='''            val sampleGpu = newFrame && (++presentedFrames % 8 == 0)
            val start = if (sampleGpu) System.nanoTime() else 0L'''
b='''            presentedFrames++
            // glFinish can serialize all queued GPU work and cause a brief
            // video hiccup. Do not force it during the first 24 decoded frames.
            // Preserve the existing performance fallback after warm start.
            val sampleGpu = newFrame && presentedFrames > 24 &&
                (presentedFrames % 8 == 0)
            val start = if (sampleGpu) System.nanoTime() else 0L'''
assert s.count(a)==1,"initial glFinish sampling anchor missing"
s=s.replace(a,b,1)
a='''            if (sampleGpu) {
                GLES30.glFinish()
                val elapsedMs = (System.nanoTime() - start) / 1_000_000.0'''
b='''            if (firstRenderedFrameNs == 0L) {
                firstRenderedFrameNs = System.nanoTime()
                Log.i("Reflite SmoothStart",
                    "First GPU presentation submitted at " +
                    ((firstRenderedFrameNs-startupNs)/1_000_000L) +
                    "ms since first decoder frame; " +
                    "model=" + if (srcH <= 800) "16-channel" else "8-channel")
            }
            if (sampleGpu) {
                GLES30.glFinish()
                val elapsedMs = (System.nanoTime() - start) / 1_000_000.0'''
assert s.count(a)==1, "render measurement anchor missing"
# Kotlin string + if expression requires parenthesis to avoid parsing issues.
b=b.replace('''"model=" + if (srcH <= 800) "16-channel" else "8-channel")''','''"model=" + (if (srcH <= 800) "16-channel" else "8-channel"))''')
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite Smooth Start: first-frame GPU stalls deferred; decoder intervals logged; duplicate redraw inference skipped.")
