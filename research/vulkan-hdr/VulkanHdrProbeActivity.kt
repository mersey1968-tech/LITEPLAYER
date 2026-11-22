package com.example.liteplayer

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Color
import android.os.Bundle
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.TextView

/**
 * Independent Vulkan WSI diagnostic. Does not touch the ExoPlayer or FSRCNNX
 * paths and never encodes/decodes video.
 */
class VulkanHdrProbeActivity : Activity() {
    private external fun nativeProbe(surface: android.view.Surface): String

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this)
        val video = SurfaceView(this)
        root.addView(video, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        val status = TextView(this).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(0xB0000000.toInt())
            textSize = 19f
            setPadding(22, 24, 22, 24)
            text = "Testing Vulkan HDR10 output... If the screen changes colour, check Bravia HDR mode."
        }
        root.addView(status, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setContentView(root)
        video.holder.addCallback(object : SurfaceHolder.Callback {
            private var started = false
            override fun surfaceCreated(holder: SurfaceHolder) {
                if (started) return
                started = true
                Thread {
                    val report = try { nativeProbe(holder.surface) }
                        catch (t: Throwable) { "Vulkan probe error: ${t.javaClass.simpleName}: ${t.message}" }
                    runOnUiThread {
                        if (!isFinishing && !isDestroyed) {
                            AlertDialog.Builder(this@VulkanHdrProbeActivity)
                                .setTitle("Shield Vulkan HDR10 test")
                                .setMessage(report)
                                .setPositiveButton("Close") { _, _ -> finish() }
                                .setCancelable(false)
                                .show()
                        }
                    }
                }.start()
            }
            override fun surfaceChanged(holder: SurfaceHolder, format: Int, w: Int, h: Int) {}
            override fun surfaceDestroyed(holder: SurfaceHolder) {}
        })
    }
    companion object {
        init { System.loadLibrary("reflite_vulkan_probe") }
    }
}
