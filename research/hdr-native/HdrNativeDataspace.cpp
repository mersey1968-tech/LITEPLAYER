#include <jni.h>
#include <android/native_window_jni.h>
#include <android/native_window.h>
#include <android/data_space.h>
#include <android/log.h>

// Operates on the Android EGL BufferQueue itself, not an EGL PQ window request.
// A successful call reports the buffer dataspace; it does not guarantee that
// SurfaceFlinger and the HDMI sink actually enter HDR10 mode.
extern "C" JNIEXPORT jint JNICALL
Java_com_example_liteplayer_HdrNativeDataspace_setHdr(
        JNIEnv* env, jclass, jobject surface) {
    if (!surface) return -100;
    ANativeWindow* window = ANativeWindow_fromSurface(env, surface);
    if (!window) return -101;
    const int result = ANativeWindow_setBuffersDataSpace(window, ADATASPACE_BT2020_PQ);
    const int current = ANativeWindow_getBuffersDataSpace(window);
    __android_log_print(ANDROID_LOG_INFO, "Reflite HDR10",
                        "native dataspace set=%d readback=%d target=%d",
                        result, current, ADATASPACE_BT2020_PQ);
    ANativeWindow_release(window);
    if (result) return result < 0 ? result : -102;
    return current == ADATASPACE_BT2020_PQ ? 1 : -103;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_example_liteplayer_HdrNativeDataspace_setSdr(
        JNIEnv* env, jclass, jobject surface) {
    if (!surface) return -100;
    ANativeWindow* window = ANativeWindow_fromSurface(env, surface);
    if (!window) return -101;
    const int result = ANativeWindow_setBuffersDataSpace(window, ADATASPACE_SRGB);
    ANativeWindow_release(window);
    return result;
}
