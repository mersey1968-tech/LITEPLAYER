"""One-time backward seek following active neural startup; retain contrast."""
from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=once(s,"                // Submitted on the GL thread; callback is not a display-present guarantee.","                if (srcH > 800) GLES30.glFinish()")
p.write_text(s)
p=root/"MainActivity.kt"
s=p.read_text()
a=s.index("                        // A paused Media3 renderer can submit")
b=s.index("                            .postDelayed({ resume() }, 800L)",a)+len("                            .postDelayed({ resume() }, 800L)")
s=s[:a]+"""                        activePlayer.playWhenReady = true
                    }
                    if (fmt.height > 800) {
                        gpu.onFirstNeuralFrame = {
                            gpu.onFirstNeuralFrame = null
                            val fps = fmt.frameRate.takeIf { it > 0f }
                                ?: videoFps.takeIf { it > 0f } ?: 24f
                            val distance = (6000.0 / fps).toLong().coerceAtLeast(1L)
                            val handler = android.os.Handler(android.os.Looper.getMainLooper())
                            val deadline = android.os.SystemClock.uptimeMillis() + 10000L
                            val rewindWhenReady = object : Runnable {
                                override fun run() {
                                    if (player !== activePlayer || scalerView !== gpu ||
                                        !referenceScalerEnabled || isFinishing ||
                                        android.os.SystemClock.uptimeMillis() >= deadline) return
                                    val position = activePlayer.currentPosition
                                    if (activePlayer.playWhenReady && activePlayer.isPlaying &&
                                        position >= distance) {
                                        activePlayer.seekTo(position - distance)
                                    } else {
                                        handler.postDelayed(this, 40L)
                                    }
                                }
                            }
                            rewindWhenReady.run()
                        }"""+s[b:]
# Remove the temporary pause on surface creation; retain the original
# play intent checks and surface fallback behavior.
s=once(s,"""            if (resume1080AfterSurface) {
                activePlayer.playWhenReady = false
                android.util.Log.i("Reflite Startup",
                    "1080p: suspend play clock until neural decoder Surface is attached")
            }
""","")
p.write_text(s)
p=root/"FsrcnnxPipeline.kt"
s=p.read_text()
s=once(s,"""                reconstructed*=1.0-shadowDepth*shadowRange;
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);""","""                reconstructed*=1.0-shadowDepth*shadowRange;
                // Gentle SDR midtone S curve, zero extra texture reads.
                // Endpoint and midpoint preservation; chroma-neutral delta
                // bounded by available RGB headroom to avoid extra clipping.
                if (uHdr < 0.5) {
                    float tone=dot(reconstructed,vec3(.2126,.7152,.0722));
                    float delta=.12*tone*(1.0-tone)*(2.0*tone-1.0);
                    float lo=min(reconstructed.r,min(reconstructed.g,reconstructed.b));
                    float hi=max(reconstructed.r,max(reconstructed.g,reconstructed.b));
                    reconstructed+=vec3(clamp(delta,-lo,1.0-hi));
                }
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);""")
p.write_text(s)
print("One-time six-frame rewind and approved contrast staged.")
