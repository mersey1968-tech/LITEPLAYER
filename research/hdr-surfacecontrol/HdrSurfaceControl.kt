package com.example.liteplayer

import android.view.Surface

/** API 29+: GLES FBO backed by 10-bit AHardwareBuffer, presented via ASurfaceControl.
 * No Vulkan. JNI functions MUST be invoked from the scaler's current GLES thread.
 */
internal object HdrSurfaceControl {
    init { System.loadLibrary("reflite_hdr_surfacecontrol") }
    @JvmStatic external fun create(parent: Surface, width: Int, height: Int): Long
    @JvmStatic external fun begin(handle: Long): Int
    @JvmStatic external fun present(handle: Long): Boolean
    @JvmStatic external fun destroy(handle: Long)
    @JvmStatic external fun snapshot(handle: Long): String
    @JvmStatic external fun lastError(): String
}
