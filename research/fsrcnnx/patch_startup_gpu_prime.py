"""Reflite startup GPU memory preparation, independent of GPU vendor.

Work from the known-smooth 16-channel v2, preserving tone, inference, audio,
video timestamps, external Plezy intent and Android app/package identity.

Android already provides the decoded SurfaceTexture BufferQueue; don't add
an uncontrolled decoded-frame delay or invent a network buffering workaround.
Allocate FSRCNNX floating-point render targets before decoder presentation.
This moves first-frame GPU memory allocation to the renderer startup phase.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
# signature is already patched by v2 warmup
a='''    fun render(video:Int,matrix:FloatArray,w:Int,h:Int,outW:Int,outH:Int,diagnostic:Boolean,hdr:Boolean=false,outputFbo:Int=0,'''
assert s.count(a)==1, f"render signature no longer matches: {s.count(a)}"
s=s.replace(a,'''    // Preallocate the neural framebuffers before the video decoder gets the
    // SurfaceTexture. All calls run on the same owning OpenGL thread.
    // No extra frame queue and no frame-time or audio-timestamp changes.
    fun prime(w: Int, h: Int) {
        ensureSize(w, h)
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
        GLES30.glFlush()
    }
'''+a,1)
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
a='''        queueEvent { srcW = w; srcH = h; surfaceTexture?.setDefaultBufferSize(w,h); allocatedW = 0 }'''
b='''        queueEvent {
            srcW = w; srcH = h
            surfaceTexture?.setDefaultBufferSize(w,h)
            allocatedW = 0
            // If the GL context is already initialized, prepare the new
            // resolution immediately. If not, onSurfaceCreated primes it.
            if (neuralPipeline != null) primeNeuralTargets()
        }'''
assert s.count(a)==1
s=s.replace(a,b,1)
# onSurfaceCreated has previously been modified by patch_v2_warmup_detail.py
a='''            if (hdrRequested && !hdrSurfaceActive) {
                val detail = hdrDiagnostic'''
b='''            // Format is normally supplied before decoder Surface creation.
            // Allocate GPU memory here, while no decoded frame is waiting.
            primeNeuralTargets()
            if (hdrRequested && !hdrSurfaceActive) {
                val detail = hdrDiagnostic'''
assert s.count(a)==1
s=s.replace(a,b,1)
a='''    override fun onSurfaceChanged(gl: GL10?, w: Int, h: Int) {'''
b='''    private fun primeNeuralTargets() {
        if (srcW !in 1..1920 || srcH !in 1..1080) return
        val target = if (srcH <= 800 && !neural16Unavailable) {
            neural16Pipeline ?: neuralPipeline
        } else neuralPipeline
        try {
            val started = System.nanoTime()
            target?.prime(srcW, srcH)
            Log.i("Reflite Startup",
                "GPU neural framebuffers prepared " + srcW + "x" + srcH +
                " in " + ((System.nanoTime()-started)/1_000_000L) +
                "ms; gpu=" + GLES30.glGetString(GLES30.GL_RENDERER))
        } catch (e: Throwable) {
            if (target === neural16Pipeline && neural16Pipeline != null) {
                Log.w("Reflite Startup",
                    "16-channel preallocation unavailable on this GPU, " +
                    "falling back to original network: " + e.message)
                neural16Pipeline?.close()
                neural16Pipeline = null
                neural16Unavailable = true
                // Leave the existing fallback's GPU surfaces untouched;
                // normal playback allocates them as needed.
            } else {
                Log.w("Reflite Startup",
                    "GPU preallocation unavailable; normal on-demand " +
                    "allocation remains in place: " + e.message)
            }
        } finally {
            GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER, 0)
        }
    }

'''+a
assert s.count(a)==1
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite v2: allocate neural GPU buffers prior to decoded playback; same renderer and no extra frame latency.")
