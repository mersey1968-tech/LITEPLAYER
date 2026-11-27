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
# Replace wall-clock rewind with a completed-frame driven callback for 1080p.
once("""                    if (fmt.height > 800) {
                        gpu.onFirstNeuralFrame = {""","""                    if (fmt.width == 1920 && fmt.height == 1080) {
                        var afrRetried = false
                        gpu.onCinemaReady = cinemaReady@{
                            if (player !== activePlayer || scalerView !== gpu ||
                                !referenceScalerEnabled || isFinishing) {
                                gpu.onCinemaReady = null
                                return@cinemaReady
                            }
                            val fps = resolvedScalerFormat()?.frameRate?.takeIf { it > 0f && it.isFinite() }
                                ?: videoFps.takeIf { it > 0f && it.isFinite() }
                                ?: return@cinemaReady
                            val hz = window.decorView.display?.refreshRate ?: return@cinemaReady
                            val multiple = kotlin.math.round(hz / fps).coerceAtLeast(1f)
                            if (kotlin.math.abs(hz - multiple * fps) > 0.15f) {
                                if (!afrRetried) {
                                    afrRetried = true
                                    lastFrameRateSurface = null
                                    applyFrameRate()
                                }
                                return@cinemaReady
                            }
                            val distance = (6000.0 / fps).toLong().coerceAtLeast(1L)
                            val position = activePlayer.currentPosition
                            if (!activePlayer.isPlaying || position < distance) return@cinemaReady
                            gpu.onCinemaReady = null
                            activePlayer.seekTo(position - distance)
                        }
                    } else if (fmt.height > 800) {
                        gpu.onFirstNeuralFrame = {""")
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
