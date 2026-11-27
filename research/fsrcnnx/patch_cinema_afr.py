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
        val cinema = referenceScalerEnabled &&
            fmt?.width == 1920 && fmt.height == 1080
        val fps = if (cinema) fmt?.frameRate?.takeIf { it > 0f && it.isFinite() } ?: videoFps else videoFps
        if (fps <= 0f || !fps.isFinite()) return
        val surface = scalerView?.holder?.surface ?: (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface""")
once("""        if (Build.VERSION.SDK_INT >= 31 && kotlin.math.abs(fps-25f) < 0.25f) {""","""        if (Build.VERSION.SDK_INT >= 31 && (cinema || kotlin.math.abs(fps-25f) < 0.25f)) {""")
# Wait on the native surface until the requested HDMI cadence is stable.
once("""    private fun applyRefliteScaler() {""","""    private var cinemaPendingPlayer: androidx.media3.common.Player? = null
    private var cinemaGatePassed = false
    private fun applyRefliteScaler() {""")
once("""            val resume1080AfterSurface = fmt.height > 800 && activePlayer.playWhenReady""","""            if (fmt.width == 1920 && fmt.height == 1080) {
                if (cinemaPendingPlayer !== activePlayer) {
                    cinemaPendingPlayer = activePlayer
                    cinemaGatePassed = false
                    val h = android.os.Handler(android.os.Looper.getMainLooper())
                    val deadline = android.os.SystemClock.uptimeMillis() + 12000L
                    var stableSince = 0L
                    var requested = false
                    val waitForMode = object : Runnable {
                        override fun run() {
                            if (player !== activePlayer || !referenceScalerEnabled || isFinishing ||
                                cinemaPendingPlayer !== activePlayer) {
                                if (cinemaPendingPlayer === activePlayer) cinemaPendingPlayer = null
                                return
                            }
                            val fps = resolvedScalerFormat()?.frameRate?.takeIf { it > 0f && it.isFinite() }
                                ?: videoFps.takeIf { it > 0f && it.isFinite() }
                            val hz = window.decorView.display?.refreshRate
                            val now = android.os.SystemClock.uptimeMillis()
                            if (fps != null && hz != null) {
                                if (!requested) {
                                    requested = true
                                    lastFrameRateSurface = null
                                    applyFrameRate()
                                }
                                val multiple = kotlin.math.round(hz / fps).coerceAtLeast(1f)
                                val match = kotlin.math.abs(hz - multiple * fps) <= 0.15f &&
                                    (kotlin.math.abs(fps - 25f) >= 0.25f || kotlin.math.abs(hz - 50f) < 0.25f)
                                if (match && activePlayer.isPlaying) {
                                    if (stableSince == 0L) stableSince = now
                                    if (now - stableSince >= 500L) {
                                        cinemaGatePassed = true
                                        applyRefliteScaler()
                                        return
                                    }
                                } else stableSince = 0L
                            }
                            if (now < deadline) h.postDelayed(this, 100L)
                            else {
                                cinemaPendingPlayer = null
                                referenceScalerEnabled = false
                                Toast.makeText(this@MainActivity, "1080p upscaling deferred: display not ready", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }
                    h.post(waitForMode)
                }
                if (!cinemaGatePassed) return
            }
            val resume1080AfterSurface = fmt.height > 800 && activePlayer.playWhenReady""")
# Once the display is settled, do not initiate another HDMI transition on overlay attachment.
once("""                    activePlayer.setVideoSurface(surface)
                    applyFrameRate()""","""                    activePlayer.setVideoSurface(surface)
                    if (!(fmt.width == 1920 && fmt.height == 1080 && cinemaGatePassed)) applyFrameRate()""")

# Replace wall-clock rewind with a completed-frame driven callback for 1080p.
once("""                    if (fmt.height > 800) {
                        gpu.onFirstNeuralFrame = {""","""                    if (fmt.width == 1920 && fmt.height == 1080) {
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
