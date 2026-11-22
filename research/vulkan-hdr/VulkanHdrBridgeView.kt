package com.example.liteplayer

import android.content.Context
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.Surface
import java.nio.ByteBuffer
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Opt-in experimental SDR-to-HDR10 display output. Keep frame submission on
 * the FSRCNNX GL thread, serialize lifecycle operations separately.
 */
class VulkanHdrBridgeView(context: Context) : SurfaceView(context) {
    private external fun nativeStart(surface: Surface): String
    private external fun nativeFrame(rgba: ByteBuffer, width: Int, height: Int): Boolean
    private external fun nativePrepareShared(width: Int, height: Int): Int
    private external fun nativePresentShared(): Boolean
    private external fun nativeReleaseSharedGL()
    private external fun nativeSharedError(): String
    private external fun nativeStop()
    private val active = AtomicBoolean(false)
    private val lifecycle = Executors.newSingleThreadExecutor()
    @Volatile private var failed = false
    @Volatile private var started = false
    @Volatile private var surfaceWidth = 0
    @Volatile private var surfaceHeight = 0
    private val firstFrame = AtomicBoolean(false)
    private var surfaceGeneration = 0
    @Volatile private var status = "HDR Vulkan surface not created"
    @Volatile private var presentCount = 0
    @Volatile private var firstPresent = false
    fun hdrSnapshot(): String = "Vulkan: $status, ready=${isReady()}, " +
        "surface=${surfaceWidth}x${surfaceHeight}, presents=$presentCount"
    private fun watchFirstFrame() {
        val generation = ++surfaceGeneration
        postDelayed({
            if (generation == surfaceGeneration && isAttachedToWindow &&
                active.get() && !failed && !firstFrame.get()) {
                reportFailure("Vulkan HDR initialized but received no video frames (12 s)")
            }
        }, 12000L)
    }
    var onFailure: ((String) -> Unit)? = null
    var onSurfaceReady: (() -> Unit)? = null

    init {
        setZOrderMediaOverlay(true)
        holder.addCallback(object : SurfaceHolder.Callback {
            override fun surfaceCreated(holder: SurfaceHolder) {
                // Queue changes in callback order, avoiding start/stop races on
                // AFR surface reconstruction.
                lifecycle.execute {
                    try {
                        active.set(false)
                        if (started) { nativeStop(); started = false }
                        status = "Creating Vulkan HDR swapchain"
                        val failure = nativeStart(holder.surface)
                        if (failure.isEmpty()) {
                            status = "HDR swapchain ready"
                            started = true
                            failed = false
                            active.set(true)
                            firstFrame.set(false)
                            post { onSurfaceReady?.invoke(); watchFirstFrame() }
                        } else {
                            failed = true
                            status = failure
                            post { onFailure?.invoke(failure) }
                        }
                    } catch (t: Throwable) {
                        failed = true
                        post { onFailure?.invoke(t.message ?: t.javaClass.simpleName) }
                    }
                }
            }
            override fun surfaceChanged(holder: SurfaceHolder, format: Int, w: Int, h: Int) {
                val changed = surfaceWidth > 0 && surfaceHeight > 0 &&
                    (surfaceWidth != w || surfaceHeight != h)
                surfaceWidth = w
                surfaceHeight = h
                if (changed) {
                    active.set(false)
                    lifecycle.execute {
                        try {
                            if (started) { nativeStop(); started = false }
                            if (!holder.surface.isValid) return@execute
                            status = "Rebuilding Vulkan HDR after mode switch"
                            val failure = nativeStart(holder.surface)
                            if (failure.isEmpty()) {
                                status = "HDR swapchain rebuilt"
                                started = true
                                failed = false
                                active.set(true)
                                firstFrame.set(false)
                                post { onSurfaceReady?.invoke(); watchFirstFrame() }
                            } else {
                                failed = true
                                status = failure
                                post { onFailure?.invoke(failure) }
                            }
                        } catch (t: Throwable) {
                            failed = true
                            post { onFailure?.invoke(t.message ?: t.javaClass.simpleName) }
                        }
                    }
                }
            }
            override fun surfaceDestroyed(holder: SurfaceHolder) {
                surfaceGeneration++
                active.set(false)
                surfaceWidth = 0
                surfaceHeight = 0
                lifecycle.execute {
                    if (started) {
                        nativeStop()
                        started = false
                    }
                }
            }
        })
    }
    fun isReady(): Boolean = active.get() && !failed
    /** GL thread only: imports the same AHardwareBuffer into GLES and Vulkan. */
    fun prepareShared(width: Int, height: Int): Int {
        if (!isReady()) return 0
        val fbo = nativePrepareShared(width, height)
        if (fbo == 0) reportFailure("Zero-copy HDR: " + nativeSharedError())
        else status = "EGL/Vulkan FP16 shared framebuffer created"
        return fbo
    }

    /** Called only after glFinish has made the shared image visible to Vulkan. */
    fun presentShared(): Boolean {
        if (!isReady()) return false
        val ok = nativePresentShared()
        if (ok) {
            firstFrame.set(true)
            presentCount++
            status = "HDR GPU frames submitted"
        }
        else reportFailure("Vulkan HDR zero-copy present: " + nativeSharedError())
        return ok
    }
    fun releaseSharedGL() = nativeReleaseSharedGL()
    private fun reportFailure(message: String) {
        if (!failed) {
            failed = true
            status = message
            active.set(false)
            post { onFailure?.invoke(message) }
        }
    }
    fun send(rgba: ByteBuffer, w: Int, h: Int): Boolean {
        if (!isReady()) return false
        val result = nativeFrame(rgba,w,h)
        if (!result && active.get() && !failed) {
            // An actual Vulkan presentation error still falls back safely.
            failed = true
            post { onFailure?.invoke("Vulkan frame transfer or presentation failed") }
        }
        return result
    }
    companion object {
        init { System.loadLibrary("reflite_vulkan_probe") }
    }
}
