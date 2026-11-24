"""Reflite-only 1080p startup synchronization.

Keep Media3 audio and video timelines together when switching decoder output
to the new neural Surface. Preallocate the existing eight-channel RGBA16F
inference targets before advertising that Surface. Suspend playWhenReady only
during the surface switch at 1080p, restoring the exact prior intent once
Media3's new surface has been supplied. Preserve all 720p paths, GPU fences,
FSRCNNX shaders, audio sinks, AFR, and Plezy identity.
"""
from pathlib import Path

p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''    fun render(video:Int,matrix:FloatArray,w:Int,h:Int,outW:Int,outH:Int,diagnostic:Boolean,hdr:Boolean=false,outputFbo:Int=0,''';
assert s.count(a)==1, "Cannot locate final neural render function"
b='''    // Allocate all RGBA16F inference targets on the GL thread before the
    // decoder Surface is offered to Media3. No pixel or timing changes.
    fun prepareTargets(w:Int,h:Int) {
        ensureSize(w,h)
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,0)
        android.util.Log.i("Reflite Startup",
            "Neural targets ready before decoder attachment: " + w + "x" + h)
    }

'''+a
s=s.replace(a,b,1)
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
a='''            if (hdrRequested && !hdrSurfaceActive) {
                val detail = hdrDiagnostic'''
b='''            // 1080p occasionally began playback while allocating eight-channel
            // neural render targets for the first decoded frame. Perform those
            // allocations before giving the decoder its replacement Surface.
            // 720p uses its known-good preparation and timing path unchanged.
            if (srcH > 800) {
                neuralPipeline?.prepareTargets(srcW,srcH)
            }
            if (hdrRequested && !hdrSurfaceActive) {
                val detail = hdrDiagnostic'''
assert s.count(a)==1,"Surface creation anchor changed"
s=s.replace(a,b,1)
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
a='''            val gpu = ReferenceScalerView(this, false)
            gpu.onHdrUnavailable'''
b='''            // A replacement video Surface arriving after playback started can
            // leave audio ahead while neural GPU initialization catches up.
            // Pause ONLY on initial 1080p neural-surface creation, retaining the
            // player's original requested play/pause state for restoration.
            val resume1080AfterSurface = fmt.height > 800 && activePlayer.playWhenReady
            if (resume1080AfterSurface) {
                activePlayer.playWhenReady = false
                android.util.Log.i("Reflite Startup",
                    "1080p: suspend play clock until neural decoder Surface is attached")
            }
            val gpu = ReferenceScalerView(this, false)
            gpu.onHdrUnavailable'''
assert s.count(a)==1,"GPU surface creation anchor changed"
s=s.replace(a,b,1)
a='''                    referenceScalerEnabled = false
                    applyRefliteScaler()
                    Toast.makeText(this, "GPU fallback: " + failure, Toast.LENGTH_LONG).show()'''
b='''                    referenceScalerEnabled = false
                    applyRefliteScaler()
                    if (resume1080AfterSurface && player === activePlayer) {
                        activePlayer.playWhenReady = true
                    }
                    Toast.makeText(this, "GPU fallback: " + failure, Toast.LENGTH_LONG).show()'''
assert s.count(a)==1,"GPU fallback restoration anchor changed"
s=s.replace(a,b,1)
a='''                    activePlayer.setVideoSurface(surface)
                    applyFrameRate()
                }
            }'''
b='''                    activePlayer.setVideoSurface(surface)
                    applyFrameRate()
                    if (resume1080AfterSurface) {
                        activePlayer.playWhenReady = true
                        android.util.Log.i("Reflite Startup",
                            "1080p: neural decoder Surface attached; resume playback")
                    }
                }
            }'''
assert s.count(a)==1,"GPU handoff anchor changed"
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite 1080p startup: preallocate 8-channel RGBA16F targets; pause only while exchanging Surface, then restore play intent. 720p unchanged.")
