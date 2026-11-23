#include <jni.h>
#include <android/native_window_jni.h>
#include <android/hardware_buffer.h>
#include <android/surface_control.h>
#include <android/data_space.h>
#include <android/log.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <GLES2/gl2ext.h>
#include <atomic>
#include <array>
#include <memory>
#include <mutex>
#include <string>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,"Reflite-SC-HDR",__VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR,"Reflite-SC-HDR",__VA_ARGS__)

namespace {
std::mutex errorMutex;
std::string lastError = "not initialized";
void error(const std::string& s) {
    std::lock_guard<std::mutex> lock(errorMutex);
    lastError = s;
    LOGE("%s", s.c_str());
}
struct Slot {
    AHardwareBuffer* hw = nullptr;
    EGLImageKHR image = EGL_NO_IMAGE_KHR;
    GLuint tex = 0;
    GLuint fbo = 0;
    std::shared_ptr<std::atomic_bool> available = std::make_shared<std::atomic_bool>(true);
};
struct Layer {
    ANativeWindow* parent = nullptr;
    ASurfaceControl* sc = nullptr;
    EGLDisplay display = EGL_NO_DISPLAY;
    PFNEGLDESTROYIMAGEKHRPROC eglDestroyImage = nullptr;
    int width = 0;
    int height = 0;
    int current = -1;
    int displayed = -1;
    int sent = 0;
    std::array<Slot,3> slots;
};
void onPreviousReleased(void* context, ASurfaceTransactionStats*) {
    auto* available = reinterpret_cast<std::shared_ptr<std::atomic_bool>*>(context);
    (*available)->store(true, std::memory_order_release);
    delete available;
}
void cleanup(Layer* layer) {
    if (!layer) return;
    // Called from the EGL render thread while its context is current.
    if (layer->sc) {
        auto* tx = ASurfaceTransaction_create();
        ASurfaceTransaction_setVisibility(tx, layer->sc, ASURFACE_TRANSACTION_VISIBILITY_HIDE);
        ASurfaceTransaction_apply(tx);
        ASurfaceTransaction_delete(tx);
        ASurfaceControl_release(layer->sc);
    }
    for (auto &s: layer->slots) {
        if (s.fbo) glDeleteFramebuffers(1,&s.fbo);
        if (s.tex) glDeleteTextures(1,&s.tex);
        if (s.image != EGL_NO_IMAGE_KHR && layer->eglDestroyImage)
            layer->eglDestroyImage(layer->display,s.image);
        if (s.hw) AHardwareBuffer_release(s.hw);
    }
    if (layer->parent) ANativeWindow_release(layer->parent);
    delete layer;
}
bool initSlot(Layer* layer, Slot& s, PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC nativeBuffer,
              PFNEGLCREATEIMAGEKHRPROC createImage,
              PFNGLEGLIMAGETARGETTEXTURE2DOESPROC imageTarget) {
    AHardwareBuffer_Desc d{};
    d.width=layer->width; d.height=layer->height; d.layers=1;
    d.format=AHARDWAREBUFFER_FORMAT_R10G10B10A2_UNORM;
    d.usage=AHARDWAREBUFFER_USAGE_GPU_COLOR_OUTPUT |
            AHARDWAREBUFFER_USAGE_GPU_SAMPLED_IMAGE |
            AHARDWAREBUFFER_USAGE_COMPOSER_OVERLAY;
    if (AHardwareBuffer_allocate(&d,&s.hw)!=0 || !s.hw) {
        error("10-bit RGBA AHardwareBuffer allocation rejected");
        return false;
    }
    EGLClientBuffer client=nativeBuffer(s.hw);
    if (!client) { error("eglGetNativeClientBufferANDROID rejected the 10-bit AHB"); return false; }
    EGLint attrs[]={EGL_IMAGE_PRESERVED_KHR,EGL_TRUE,EGL_NONE};
    s.image=createImage(layer->display,EGL_NO_CONTEXT,EGL_NATIVE_BUFFER_ANDROID,client,attrs);
    if (s.image==EGL_NO_IMAGE_KHR) {
        error("eglCreateImageKHR 10-bit AHardwareBuffer import failed EGL error="+std::to_string(eglGetError()));
        return false;
    }
    glGenTextures(1,&s.tex);
    glBindTexture(GL_TEXTURE_2D,s.tex);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    imageTarget(GL_TEXTURE_2D,reinterpret_cast<GLeglImageOES>(s.image));
    glGenFramebuffers(1,&s.fbo);
    glBindFramebuffer(GL_FRAMEBUFFER,s.fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,s.tex,0);
    GLenum status=glCheckFramebufferStatus(GL_FRAMEBUFFER);
    if (status!=GL_FRAMEBUFFER_COMPLETE) {
        error("10-bit EGLImage framebuffer incomplete status="+std::to_string(status));
        return false;
    }
    return true;
}
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_example_liteplayer_HdrSurfaceControl_create(JNIEnv* env,jclass,jobject surface,jint width,jint height) {
    if (width<16 || height<16 || !surface) {error("Invalid output surface/size");return 0;}
    auto* layer=new Layer;
    layer->width=width;layer->height=height;
    layer->parent=ANativeWindow_fromSurface(env,surface);
    if (!layer->parent) {error("SurfaceView parent ANativeWindow unavailable");cleanup(layer);return 0;}
    layer->display=eglGetCurrentDisplay();
    if (layer->display==EGL_NO_DISPLAY || eglGetCurrentContext()==EGL_NO_CONTEXT) {
        error("No current EGL context on FSRCNNX thread");cleanup(layer);return 0;
    }
    const char* extensions=eglQueryString(layer->display,EGL_EXTENSIONS);
    std::string ext=extensions?extensions:"";
    if (ext.find("EGL_ANDROID_get_native_client_buffer")==std::string::npos ||
        ext.find("EGL_ANDROID_image_native_buffer")==std::string::npos) {
        error("Shield EGL lacks Android native buffer image extensions");cleanup(layer);return 0;
    }
    auto nativeBuffer=reinterpret_cast<PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC>(
        eglGetProcAddress("eglGetNativeClientBufferANDROID"));
    auto createImage=reinterpret_cast<PFNEGLCREATEIMAGEKHRPROC>(eglGetProcAddress("eglCreateImageKHR"));
    layer->eglDestroyImage=reinterpret_cast<PFNEGLDESTROYIMAGEKHRPROC>(eglGetProcAddress("eglDestroyImageKHR"));
    auto imageTarget=reinterpret_cast<PFNGLEGLIMAGETARGETTEXTURE2DOESPROC>(
        eglGetProcAddress("glEGLImageTargetTexture2DOES"));
    if (!nativeBuffer || !createImage || !layer->eglDestroyImage || !imageTarget) {
        error("Required EGLImage extension functions unavailable");cleanup(layer);return 0;
    }
    layer->sc=ASurfaceControl_createFromWindow(layer->parent,"Reflite-neural-HDR10-10bit");
    if(!layer->sc) {error("ASurfaceControl_createFromWindow rejected GLSurfaceView parent");cleanup(layer);return 0;}
    for(auto &s:layer->slots)
        if(!initSlot(layer,s,nativeBuffer,createImage,imageTarget)){cleanup(layer);return 0;}
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    error("SurfaceControl created; 3 x 10-bit GPU framebuffer imports succeeded; HDMI HDR unverified");
    LOGI("10-bit SurfaceControl GPU buffers ready %dx%d",width,height);
    return reinterpret_cast<jlong>(layer);
}

extern "C" JNIEXPORT jint JNICALL
Java_com_example_liteplayer_HdrSurfaceControl_begin(JNIEnv*,jclass,jlong ptr) {
    auto* layer=reinterpret_cast<Layer*>(ptr);
    if(!layer || layer->current>=0)return 0;
    for(int n=0;n<3;++n) {
        int i=(layer->sent+n)%3;
        if(i==layer->displayed)continue;
        bool expected=true;
        if(layer->slots[i].available->compare_exchange_strong(expected,false)) {
            layer->current=i;
            return static_cast<jint>(layer->slots[i].fbo);
        }
    }
    // No free buffer: skip the video output frame instead of blocking audio.
    return 0;
}
extern "C" JNIEXPORT jboolean JNICALL
Java_com_example_liteplayer_HdrSurfaceControl_present(JNIEnv*,jclass,jlong ptr) {
    auto* layer=reinterpret_cast<Layer*>(ptr);
    if(!layer || layer->current<0)return JNI_FALSE;
    glFinish(); // conservative prototype; replace with native fence in optimized version
    if(glGetError()!=GL_NO_ERROR){error("GPU error on HDR10 output framebuffer");layer->slots[layer->current].available->store(true);layer->current=-1;return JNI_FALSE;}
    int next=layer->current, prev=layer->displayed;
    auto* tx=ASurfaceTransaction_create();
    ASurfaceTransaction_setBuffer(tx,layer->sc,layer->slots[next].hw,-1);
    ASurfaceTransaction_setBufferDataSpace(tx,layer->sc,ADATASPACE_BT2020_PQ);
    ARect source{0,0,layer->width,layer->height};
    ARect dest{0,0,layer->width,layer->height};
    ASurfaceTransaction_setGeometry(tx,layer->sc,source,dest,0);
    ASurfaceTransaction_setZOrder(tx,layer->sc,1);
    ASurfaceTransaction_setVisibility(tx,layer->sc,ASURFACE_TRANSACTION_VISIBILITY_SHOW);
    if(prev>=0) {
        auto* released=new std::shared_ptr<std::atomic_bool>(layer->slots[prev].available);
        ASurfaceTransaction_setOnComplete(tx,released,onPreviousReleased);
    }
    ASurfaceTransaction_apply(tx);
    ASurfaceTransaction_delete(tx);
    layer->displayed=next;
    layer->current=-1;
    layer->sent=(next+1)%3;
    return JNI_TRUE;
}
extern "C" JNIEXPORT void JNICALL
Java_com_example_liteplayer_HdrSurfaceControl_destroy(JNIEnv*,jclass,jlong ptr) {
    cleanup(reinterpret_cast<Layer*>(ptr));
}
extern "C" JNIEXPORT jstring JNICALL
Java_com_example_liteplayer_HdrSurfaceControl_lastError(JNIEnv* env,jclass) {
    std::lock_guard<std::mutex> lock(errorMutex);
    return env->NewStringUTF(lastError.c_str());
}
