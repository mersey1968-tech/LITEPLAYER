from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
p=root/"MainActivity.kt"
s=p.read_text()
# Move callback installation before handing the decoder its surface.
a=s.index("                    if (fmt.height > 800) {\n                        gpu.onFirstNeuralFrame = {")
b=s.index("                            rewindWhenReady.run()",a)
b=s.index("\n                    }",b)+len("\n                    }")
callback=s[a:b]
s=s[:a]+s[b:]
anchor="                    activePlayer.setVideoSurface(surface)"
assert s.count(anchor)==1
s=s.replace(anchor,callback+"\n"+anchor,1)
# Resolve FPS at the actual seek, not at early surface creation.
a="""                            val fps = fmt.frameRate.takeIf { it > 0f }
                                ?: videoFps.takeIf { it > 0f } ?: 24f
                            val distance = (6000.0 / fps).toLong().coerceAtLeast(1L)
"""
assert s.count(a)==1
s=s.replace(a,"",1)
a="                                    val position = activePlayer.currentPosition"
assert s.count(a)==1
s=s.replace(a,"""                                    val fps = resolvedScalerFormat()?.frameRate?.takeIf { it > 0f && it.isFinite() }
                                        ?: videoFps.takeIf { it > 0f && it.isFinite() }
                                    if (fps == null) {
                                        handler.postDelayed(this, 40L)
                                        return
                                    }
                                    val distance = (6000.0 / fps).toLong().coerceAtLeast(1L)
                                    val position = activePlayer.currentPosition""",1)
# Explicit refresh request after successful first frame, and again after seek.
a="                            gpu.onFirstNeuralFrame = null"
assert s.count(a)==1
s=s.replace(a,a+"\n                            lastFrameRateSurface = null\n                            applyFrameRate()",1)
# Avoid rejecting same-rate requests when system has changed modes.
a="        if (surface === lastFrameRateSurface && abs(fps - lastRequestedFrameRate) < 0.001f) return"
assert s.count(a)==1
s=s.replace(a,"        if (!cinema && surface === lastFrameRateSurface && abs(fps - lastRequestedFrameRate) < 0.001f) return",1)
p.write_text(s)
print("Startup callback registered before decoder handoff; current source FPS used at rewind; AFR reapplied.")
