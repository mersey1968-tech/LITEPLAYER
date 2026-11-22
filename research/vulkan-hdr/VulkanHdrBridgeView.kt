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
    private external fun nativeStop()
    private val active = AtomicBoolean(false)
    private val lifecycle = Executors.newSingleThreadExecutor()
    @Volatile private var failed = false
    @Volatile private var started = false
    @Volatile private var surfaceWidth = 0
    @Volatile private var surfaceHeight = 0
    var onFailure: ((String) -> Unit)? = null

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
                        val failure = nativeStart(holder.surface)
                        if (failure.isEmpty()) {
                            started = true
                            failed = false
                            active.set(true)
                        } else {
                            failed = true
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
                            val failure = nativeStart(holder.surface)
                            if (failure.isEmpty()) {
                                started = true
                                failed = false
                                active.set(true)
                            } else {
                                failed = true
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
