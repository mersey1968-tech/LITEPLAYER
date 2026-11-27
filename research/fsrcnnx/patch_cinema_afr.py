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
# Arm a bounded one-time rewind on surface handoff, independent of first-frame callback.
once("""                    if (fmt.height > 800) {
                        gpu.onFirstNeuralFrame = {""","""                    if (fmt.height > 800) {
                        val scheduleStableRewind = {""")
once("""                            val deadline = android.os.SystemClock.uptimeMillis() + 10000L""","""                            val deadline = android.os.SystemClock.uptimeMillis() + 15000L
                            var stableSince = 0L""")
once("""                                    if (activePlayer.playWhenReady && activePlayer.isPlaying &&
                                        position >= distance) {
                                        activePlayer.seekTo(position - distance)
                                    } else {
                                        handler.postDelayed(this, 40L)
                                    }""","""                                    val now = android.os.SystemClock.uptimeMillis()
                                    if (activePlayer.playWhenReady && activePlayer.isPlaying &&
                                        position >= distance) {
                                        if (stableSince == 0L) stableSince = now
                                        if (now - stableSince >= 1500L) {
                                            activePlayer.seekTo(position - distance)
                                            return
                                        }
                                    } else stableSince = 0L
                                    handler.postDelayed(this, 100L)""")
once("""                            rewindWhenReady.run()
                        }
                    }""","""                            handler.postDelayed(rewindWhenReady, 500L)
                        }
                        scheduleStableRewind()
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
