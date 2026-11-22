package com.example.liteplayer

import android.content.Context
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.Surface
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Experimental SDR-to-HDR10 display-only output. GPU-based FSRCNNX is still
 * calculated by ReferenceScalerView. No video encoding is involved.
 *
 * The initial interoperability route uses RGBA readback, so it may not be able
 * to sustain 1080p playback. This is opt-in and SDR is the unchanged default.
 */
class VulkanHdrBridgeView(context: Context) : SurfaceView(context) {
    private external fun nativeStart(surface: Surface): String
    private external fun nativeFrame(rgba: ByteBuffer, width: Int, height: Int): Boolean
    private external fun nativeStop()
    private val active = AtomicBoolean(false)
    @Volatile private var failed = false
    var onFailure: ((String) -> Unit)? = null
    @Volatile private var started = false

    init {
        setZOrderMediaOverlay(true)
        holder.addCallback(object : SurfaceHolder.Callback {
            override fun surfaceCreated(holder: SurfaceHolder) {
                Thread {
                    try {
                        val failure = nativeStart(holder.surface)
                        if (failure.isEmpty()) {
                            active.set(true)
                            started = true
                        } else {
                            failed = true
                            post { onFailure?.invoke(failure) }
                        }
                    } catch (t: Throwable) {
                        failed = true
                        post { onFailure?.invoke(t.message ?: t.javaClass.simpleName) }
                    }
                }.start()
            }
            override fun surfaceChanged(holder: SurfaceHolder, format: Int, w: Int, h: Int) {}
            override fun surfaceDestroyed(holder: SurfaceHolder) {
                active.set(false)
                // Frame production runs on the Reflite GL thread.
                // Synchronization of the native Vulkan resources is internal.
                Thread { if (started) nativeStop() }.start()
            }
        })
    }

    fun isReady(): Boolean = active.get() && !failed
    fun send(rgba: ByteBuffer, w: Int, h: Int): Boolean {
        if (!isReady()) return false
        val result = nativeFrame(rgba, w, h)
        if (!result && !failed) {
            failed = true
            post { onFailure?.invoke("Vulkan frame transfer or presentation failed") }
        }
        return result
    }

    companion object {
        init { System.loadLibrary("reflite_vulkan_probe") }
    }
}
