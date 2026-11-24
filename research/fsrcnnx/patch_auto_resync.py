"""One-shot 1080p neural playback synchronization seek, Reflite only."""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
a='''                        var waitingForNeuralFrame = true
                        val resume = {'''
b='''                        var waitingForNeuralFrame = true
                        var autoSyncIssued = false
                        val autoSyncHandler = android.os.Handler(android.os.Looper.getMainLooper())
                        val startupItem = activePlayer.currentMediaItem
                        var startupPlaybackPosition = activePlayer.currentPosition
                        var checksRemaining = 20
                        val autoSync = object : Runnable {
                            override fun run() {
                                if (autoSyncIssued || player !== activePlayer ||
                                    scalerView !== gpu || !referenceScalerEnabled ||
                                    isFinishing || activePlayer.currentMediaItem != startupItem ||
                                    !activePlayer.playWhenReady) return
                                val format = resolvedScalerFormat() ?: return
                                if (format.height <= 800) return
                                val pos = activePlayer.currentPosition
                                val advanced = pos - startupPlaybackPosition
                                // Abort if an intervening manual seek clearly changed position.
                                if (advanced < -100L || advanced > 6000L) return
                                if (activePlayer.isPlaying && advanced >= 1000L) {
                                    autoSyncIssued = true
                                    // Replicate the observed successful manual rewind.
                                    // This intentionally replays just 250 ms once.
                                    val target = (pos - 250L).coerceAtLeast(0L)
                                    android.util.Log.i("Reflite Startup",
                                        "1080p one-time sync seek: " + pos + " -> " + target)
                                    activePlayer.seekTo(target)
                                } else if (--checksRemaining > 0) {
                                    autoSyncHandler.postDelayed(this, 250L)
                                }
                            }
                        }
                        val resume = {'''
assert s.count(a)==1, "Precision Sync resume anchor changed"
s=s.replace(a,b,1)
a='''                                    activePlayer.playWhenReady = true
                                }
                            }
                        }
                        gpu.onFirstNeuralFrame'''
b='''                                    startupPlaybackPosition = activePlayer.currentPosition
                                    activePlayer.playWhenReady = true
                                    autoSyncHandler.postDelayed(autoSync, 1250L)
                                }
                            }
                        }
                        gpu.onFirstNeuralFrame'''
assert s.count(a)==1, "Precision Sync playback anchor changed"
s=s.replace(a,b,1)
p.write_text(s)
print("1080p neural startup: one guarded synchronization rewind, no shader or audio-sink changes.")
