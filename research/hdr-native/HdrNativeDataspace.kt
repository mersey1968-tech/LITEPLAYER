package com.example.liteplayer

import android.view.Surface

/** Reflite-only opt-in native HDR10 dataspace presentation experiment.
 * A successful buffer-queue dataspace request is not a display HDR confirmation.
 */
internal object HdrNativeDataspace {
    init { System.loadLibrary("reflite_hdr_dataspace") }
    @JvmStatic external fun setHdr(surface: Surface): Int
    @JvmStatic external fun setSdr(surface: Surface): Int
}
