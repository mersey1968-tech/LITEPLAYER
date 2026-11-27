from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)
once("""        val fps = videoFps
        if (fps <= 0f) return
        val surface = scalerView?.holder?.surface ?: (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface""","""        val fmt = resolvedScalerFormat()
        val cinema = referenceScalerEnabled && scalerView != null &&
            fmt?.width == 1920 && fmt.height == 1080
        val fps = if (cinema) fmt?.frameRate?.takeIf { it > 0f && it.isFinite() } ?: videoFps else videoFps
        if (fps <= 0f || !fps.isFinite()) return
        val surface = scalerView?.holder?.surface ?: (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface""")
once("""        if (Build.VERSION.SDK_INT >= 31 && kotlin.math.abs(fps-25f) < 0.25f) {""","""        if (Build.VERSION.SDK_INT >= 31 && (cinema || kotlin.math.abs(fps-25f) < 0.25f)) {""")
# Reapply only after the existing six-frame rewind. No extra seek.
once("""                                        activePlayer.seekTo(position - distance)""","""                                        activePlayer.seekTo(position - distance)
                                        if (fmt.width == 1920 && fmt.height == 1080) {
                                            handler.postDelayed({
                                                if (player === activePlayer && scalerView === gpu &&
                                                    referenceScalerEnabled && !isFinishing) {
                                                    lastFrameRateSurface = null
                                                    applyFrameRate()
                                                }
                                            }, 350L)
                                        }""")
# Guard against asynchronous estimated FPS overwriting known source metadata.
once("""            if (found > 0f) runOnUiThread { videoFps = found; applyFrameRate() }""","""            if (found > 0f) runOnUiThread {
                val fmt = resolvedScalerFormat()
                val declared = fmt?.frameRate?.takeIf { it > 0f && it.isFinite() }
                if (referenceScalerEnabled && fmt?.width == 1920 && fmt.height == 1080 && declared != null) {
                    videoFps = declared
                } else videoFps = found
                applyFrameRate()
            }""")
p.write_text(s)
print("Cinema AFR: explicit matching display mode, source metadata preference and guarded re-request after existing rewind.")
