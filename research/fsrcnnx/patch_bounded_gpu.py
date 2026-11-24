"""Bound neural work in flight and retain per-frame release deadlines.
This is a conservative queue experiment, not a decoder lead-time scheduler.
"""
from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
p=root/"MainActivity.kt"
s=p.read_text()
s=once(s,"    private val frameListener = VideoFrameMetadataListener { pts, _, _, _ ->","""    @Volatile private var neuralTimingView: ReferenceScalerView? = null
    private val frameListener = VideoFrameMetadataListener { pts, releaseNs, _, _ ->
        neuralTimingView?.recordRelease(pts, releaseNs)""")
s=once(s,"            scalerView = gpu","            scalerView = gpu\n            neuralTimingView = gpu")
s=once(s,"                scalerView = null","                scalerView = null\n                neuralTimingView = null") if s.count("                scalerView = null")==1 else s
# Clear the timing target on both teardown and failed attachment.
s=s.replace("                scalerView = null\n","                scalerView = null\n                neuralTimingView = null\n")
s=s.replace("                neuralTimingView = null\n                neuralTimingView = null\n","                neuralTimingView = null\n")
p.write_text(s)
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=once(s,"    private var firstNeuralFrameReported = false","""    private var firstNeuralFrameReported = false
    private val releaseTimes = java.util.LinkedHashMap<Long, Long>()
    private var gpuFence = 0L
    private var gpuStartNs = 0L
    private var gpuSample = false
    private var lastCompletedNs = 0L

    fun recordRelease(ptsUs: Long, releaseNs: Long) {
        synchronized(releaseTimes) {
            // MediaCodec SurfaceTexture timestamps may be PTS or release time;
            // retain both as exact keys. Never infer a clock offset.
            releaseTimes[ptsUs * 1000L] = releaseNs
            releaseTimes[releaseNs] = releaseNs
            while (releaseTimes.size > 96) {
                val it = releaseTimes.entries.iterator()
                it.next()
                it.remove()
            }
        }
    }

    private fun deadlineFor(ts: Long): Long? = synchronized(releaseTimes) {
        releaseTimes[ts]
    }""")
s=once(s,"            failed = false","""            failed = false
            gpuFence = 0L
            lastCompletedNs = 0L""")
# Never skip a draw after GLSurfaceView has obtained a window buffer: an
# unconditional swap could expose an undefined back buffer. Instead retain
# one outstanding inference and use a bounded wait only when necessary.
s=once(s,"            val newFrame = pending.getAndSet(false)","""            var completedMs: Double? = null
            if (srcH > 800 && gpuFence != 0L) {
                var state = GLES30.glClientWaitSync(gpuFence, 0, 0L)
                // If inference is still in flight, wait for that one frame,
                // before latching the newest decoder image. Do not queue another.
                while (state == GLES30.GL_TIMEOUT_EXPIRED) {
                    state = GLES30.glClientWaitSync(gpuFence,
                        GLES30.GL_SYNC_FLUSH_COMMANDS_BIT, 5_000_000L)
                }
                check(state != GLES30.GL_WAIT_FAILED) { "GPU fence wait failed" }
                val done = System.nanoTime()
                lastCompletedNs = done - gpuStartNs
                if (gpuSample) completedMs = lastCompletedNs / 1_000_000.0
                GLES30.glDeleteSync(gpuFence)
                gpuFence = 0L
            }
            val newFrame = pending.getAndSet(false)""")
s=once(s,"            val start = if (sampleGpu) System.nanoTime() else 0L","""            val start = if (sampleGpu || srcH > 800) System.nanoTime() else 0L
            val deadline = if (newFrame && srcH > 800)
                deadlineFor(surfaceTexture?.timestamp ?: Long.MIN_VALUE) else null""")
s=once(s,"            if (sampleGpu) {\n                GLES30.glFinish()\n                val elapsedMs = (System.nanoTime() - start) / 1_000_000.0","""            if (srcH > 800) {
                gpuFence = GLES30.glFenceSync(GLES30.GL_SYNC_GPU_COMMANDS_COMPLETE, 0)
                check(gpuFence != 0L) { "GPU fence creation failed" }
                gpuStartNs = start
                gpuSample = sampleGpu
                GLES30.glFlush()
                // EGL presentation time is a requested timestamp, not proof of
                // scanout. Preserve the original deadline when it is still future.
                if (deadline != null && deadline > System.nanoTime()) {
                    val d = android.opengl.EGL14.eglGetCurrentDisplay()
                    val surf = android.opengl.EGL14.eglGetCurrentSurface(android.opengl.EGL14.EGL_DRAW)
                    if (d != android.opengl.EGL14.EGL_NO_DISPLAY && surf != android.opengl.EGL14.EGL_NO_SURFACE) {
                        android.opengl.EGLExt.eglPresentationTimeANDROID(d, surf, deadline)
                    }
                }
            }
            if ((srcH <= 800 && sampleGpu) || completedMs != null) {
                val elapsedMs = completedMs ?: run {
                    GLES30.glFinish()
                    (System.nanoTime() - start) / 1_000_000.0
                }""")
s=once(s,"            neuralPipeline=null","""            neuralPipeline=null
            if (gpuFence != 0L) {
                GLES30.glDeleteSync(gpuFence)
                gpuFence = 0L
            }
            synchronized(releaseTimes) { releaseTimes.clear() }""")
p.write_text(s)
print("1080p GPU queue bounded to one inference; exact timestamp matches only; original 720p path retained.")
