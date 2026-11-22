#define VK_USE_PLATFORM_ANDROID_KHR 1
#include <vulkan/vulkan.h>
#include <android/native_window_jni.h>
#include <android/hardware_buffer.h>
#include <android/hardware_buffer_jni.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <GLES2/gl2ext.h>
#include <jni.h>
#include <vector>
#include <mutex>
#include <cmath>
#include <cstring>
#include <algorithm>
#include <cstdint>
#include <android/log.h>

#define LOG(...) __android_log_print(ANDROID_LOG_WARN,"RefliteVulkan",__VA_ARGS__)
struct HdrBridge {
    ANativeWindow* window=nullptr;
    VkInstance instance=VK_NULL_HANDLE;
    VkSurfaceKHR surface=VK_NULL_HANDLE;
    VkPhysicalDevice gpu=VK_NULL_HANDLE;
    VkDevice device=VK_NULL_HANDLE;
    uint32_t queueFamily=0,memoryType=0;
    VkQueue queue=VK_NULL_HANDLE;
    VkSwapchainKHR swapchain=VK_NULL_HANDLE;
    VkExtent2D extent{};
    VkFormat format=VK_FORMAT_UNDEFINED;
    VkCommandPool pool=VK_NULL_HANDLE;
    VkCommandBuffer cmd=VK_NULL_HANDLE;
    VkSemaphore acquire=VK_NULL_HANDLE,render=VK_NULL_HANDLE;
    AHardwareBuffer* shared=nullptr;
    EGLDisplay eglDisplay=EGL_NO_DISPLAY;
    EGLImageKHR eglImage=EGL_NO_IMAGE_KHR;
    GLuint glTexture=0,glFramebuffer=0;
    VkImage sharedImage=VK_NULL_HANDLE;
    VkDeviceMemory sharedMemory=VK_NULL_HANDLE;
    bool zeroCopySupported=false;
    uint32_t sharedW=0,sharedH=0;
    VkImage source=VK_NULL_HANDLE;
    VkDeviceMemory sourceMemory=VK_NULL_HANDLE;
    VkBuffer upload=VK_NULL_HANDLE;
    VkDeviceMemory uploadMemory=VK_NULL_HANDLE;
    void* uploadMapped=nullptr;
    uint32_t w=0,h=0;
    std::vector<VkImage> swapImages;
    std::vector<float> gamma;
    std::vector<uint16_t> pq;
    std::mutex guard;
    bool ready=false;
    std::string error;
    // The EGL texture/FBO must be deleted on the owning GL thread.
    void releaseSharedVulkan(){
        if(device){vkDeviceWaitIdle(device);
            if(sharedImage)vkDestroyImage(device,sharedImage,nullptr);
            if(sharedMemory)vkFreeMemory(device,sharedMemory,nullptr);
        }
        sharedImage=VK_NULL_HANDLE;sharedMemory=VK_NULL_HANDLE;
        if(shared)AHardwareBuffer_release(shared);
        shared=nullptr;sharedW=0;sharedH=0;
    }
    void destroy(){
        releaseSharedVulkan();
        ready=false;
        if(device){
            vkDeviceWaitIdle(device);
            if(acquire)vkDestroySemaphore(device,acquire,nullptr);
            if(render)vkDestroySemaphore(device,render,nullptr);
            if(pool)vkDestroyCommandPool(device,pool,nullptr);
            if(uploadMapped)vkUnmapMemory(device,uploadMemory);
            if(upload)vkDestroyBuffer(device,upload,nullptr);
            if(uploadMemory)vkFreeMemory(device,uploadMemory,nullptr);
            if(source)vkDestroyImage(device,source,nullptr);
            if(sourceMemory)vkFreeMemory(device,sourceMemory,nullptr);
            if(swapchain)vkDestroySwapchainKHR(device,swapchain,nullptr);
            vkDestroyDevice(device,nullptr);
        }
        if(surface&&instance)vkDestroySurfaceKHR(instance,surface,nullptr);
        if(instance)vkDestroyInstance(instance,nullptr);
        if(window)ANativeWindow_release(window);
        instance=VK_NULL_HANDLE;device=VK_NULL_HANDLE;surface=VK_NULL_HANDLE;
        zeroCopySupported=false;
        window=nullptr;swapchain=VK_NULL_HANDLE;pool=VK_NULL_HANDLE;
        upload=VK_NULL_HANDLE;uploadMemory=VK_NULL_HANDLE;uploadMapped=nullptr;
        source=VK_NULL_HANDLE;sourceMemory=VK_NULL_HANDLE;
        acquire=VK_NULL_HANDLE;render=VK_NULL_HANDLE;w=0;h=0;
        swapImages.clear();
    }
    uint32_t findMemory(uint32_t bits,VkMemoryPropertyFlags flags){
        VkPhysicalDeviceMemoryProperties mem{};
        vkGetPhysicalDeviceMemoryProperties(gpu,&mem);
        for(uint32_t i=0;i<mem.memoryTypeCount;i++)
            if((bits&(1u<<i)) && (mem.memoryTypes[i].propertyFlags&flags)==flags)return i;
        return UINT32_MAX;
    }
    static uint16_t half(float x){
        uint32_t v;std::memcpy(&v,&x,sizeof(v));
        uint32_t sign=(v>>16)&0x8000,exp=(v>>23)&255,mant=v&0x7fffff;
        if(exp<=112)return (uint16_t)sign;
        if(exp>=143)return (uint16_t)(sign|0x7bff);
        return (uint16_t)(sign|((exp-112)<<10)|(mant>>13));
    }
    void prepareLut(){
        gamma.resize(256);pq.resize(65536);
        for(int i=0;i<256;i++){
            float v=i/255.f;
            gamma[i]=(v<=0.04045f)?v/12.92f:std::pow((v+0.055f)/1.055f,2.4f);
        }
        for(int i=0;i<65536;i++){
            float v=i/65535.f;
            // Preserve diffuse whites near 203 nits and expand bright highlights.
            float knee=std::max(0.f,std::min(1.f,(v-0.65f)/0.35f));
            float nits=v*203.f+797.f*knee*knee*knee;
            float p=std::pow(nits/10000.f,2610.f/16384.f);
            float pqv=std::pow((3424.f/4096.f+(2413.f/128.f)*p)/
                (1.f+(2392.f/128.f)*p),2523.f/32.f);
            pq[i]=half(pqv);
        }
    }
    bool initialize(JNIEnv* env,jobject javaSurface){
        window=ANativeWindow_fromSurface(env,javaSurface);
        if(!window){error="No output surface";return false;}
        const char* ext[]={VK_KHR_SURFACE_EXTENSION_NAME,VK_KHR_ANDROID_SURFACE_EXTENSION_NAME,
            VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME};
        VkApplicationInfo app{};app.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app.apiVersion=VK_API_VERSION_1_0;
        VkInstanceCreateInfo ic{};ic.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        ic.pApplicationInfo=&app;ic.enabledExtensionCount=3;ic.ppEnabledExtensionNames=ext;
        if(vkCreateInstance(&ic,nullptr,&instance)!=VK_SUCCESS){error="Vulkan instance";return false;}
        VkAndroidSurfaceCreateInfoKHR ai{};ai.sType=VK_STRUCTURE_TYPE_ANDROID_SURFACE_CREATE_INFO_KHR;ai.window=window;
        if(vkCreateAndroidSurfaceKHR(instance,&ai,nullptr,&surface)!=VK_SUCCESS){error="Vulkan Android surface";return false;}
        uint32_t n=0;vkEnumeratePhysicalDevices(instance,&n,nullptr);
        if(!n){error="No Vulkan GPU";return false;}
        std::vector<VkPhysicalDevice> devices(n);vkEnumeratePhysicalDevices(instance,&n,devices.data());
        for(auto candidate:devices){
            uint32_t count=0;vkGetPhysicalDeviceQueueFamilyProperties(candidate,&count,nullptr);
            std::vector<VkQueueFamilyProperties> q(count);
            vkGetPhysicalDeviceQueueFamilyProperties(candidate,&count,q.data());
            for(uint32_t i=0;i<count;i++){
                VkBool32 present=VK_FALSE;vkGetPhysicalDeviceSurfaceSupportKHR(candidate,i,surface,&present);
                if(present && (q[i].queueFlags&VK_QUEUE_GRAPHICS_BIT)){
                    gpu=candidate;queueFamily=i;break;
                }
            }
            if(gpu)break;
        }
        if(!gpu){error="No Vulkan present queue";return false;}
        uint32_t nf=0;vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&nf,nullptr);
        std::vector<VkSurfaceFormatKHR> formats(nf);
        vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&nf,formats.data());
        // The tested Shield specifically advertised HDR10 PQ with FP16 (format 97).
        bool found=false;
        for(auto f:formats)if(f.colorSpace==VK_COLOR_SPACE_HDR10_ST2084_EXT &&
          f.format==VK_FORMAT_R16G16B16A16_SFLOAT){format=f.format;found=true;break;}
        if(!found){error="FP16 HDR10 ST2084 Vulkan swapchain not advertised";return false;}
        VkSurfaceCapabilitiesKHR caps{};
        if(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(gpu,surface,&caps)!=VK_SUCCESS){error="Surface capabilities";return false;}
        if(!(caps.supportedUsageFlags&VK_IMAGE_USAGE_TRANSFER_DST_BIT)){error="HDR10 swapchain forbids transfer destination";return false;}
        VkFormatProperties props{};vkGetPhysicalDeviceFormatProperties(gpu,format,&props);
        if(!(props.optimalTilingFeatures&VK_FORMAT_FEATURE_BLIT_SRC_BIT) ||
           !(props.optimalTilingFeatures&VK_FORMAT_FEATURE_BLIT_DST_BIT)){
            error="FP16 Vulkan blit not supported";return false;
        }
        float priority=1.f;
        VkDeviceQueueCreateInfo qi{};qi.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        qi.queueFamilyIndex=queueFamily;qi.queueCount=1;qi.pQueuePriorities=&priority;

        uint32_t extensionCount=0;
        vkEnumerateDeviceExtensionProperties(gpu,nullptr,&extensionCount,nullptr);
        std::vector<VkExtensionProperties> properties(extensionCount);
        vkEnumerateDeviceExtensionProperties(gpu,nullptr,&extensionCount,properties.data());
        bool ahb=false;
        for(auto& e:properties) if(strcmp(e.extensionName,
            VK_ANDROID_EXTERNAL_MEMORY_ANDROID_HARDWARE_BUFFER_EXTENSION_NAME)==0) ahb=true;
        zeroCopySupported=ahb;
        if(!ahb){error="Shield Vulkan driver does not expose Android hardware-buffer external memory";return false;}
        const char* enabledExts[]={
            VK_KHR_SWAPCHAIN_EXTENSION_NAME,
            VK_ANDROID_EXTERNAL_MEMORY_ANDROID_HARDWARE_BUFFER_EXTENSION_NAME,
            VK_KHR_EXTERNAL_MEMORY_EXTENSION_NAME,
            VK_KHR_SAMPLER_YCBCR_CONVERSION_EXTENSION_NAME
        };
        VkDeviceCreateInfo di{};di.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        di.queueCreateInfoCount=1;di.pQueueCreateInfos=&qi;
        di.enabledExtensionCount=4;di.ppEnabledExtensionNames=enabledExts;
        if(vkCreateDevice(gpu,&di,nullptr,&device)!=VK_SUCCESS){error="Vulkan device";return false;}
        vkGetDeviceQueue(device,queueFamily,0,&queue);
        extent=caps.currentExtent;
        if(extent.width==UINT32_MAX){
            extent.width=std::max(caps.minImageExtent.width,std::min(caps.maxImageExtent.width,
                 (uint32_t)ANativeWindow_getWidth(window)));
            extent.height=std::max(caps.minImageExtent.height,std::min(caps.maxImageExtent.height,
                 (uint32_t)ANativeWindow_getHeight(window)));
        }
        uint32_t count=caps.minImageCount+1;
        if(caps.maxImageCount && count>caps.maxImageCount)count=caps.maxImageCount;
        VkCompositeAlphaFlagBitsKHR alpha=VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
        if(!(caps.supportedCompositeAlpha&alpha)){
            for(uint32_t bit=1;bit<=8;bit<<=1)if(caps.supportedCompositeAlpha&bit){
                alpha=(VkCompositeAlphaFlagBitsKHR)bit;break;
            }
        }
        VkSwapchainCreateInfoKHR si{};
        si.sType=VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;si.surface=surface;
        si.minImageCount=count;si.imageFormat=format;si.imageColorSpace=VK_COLOR_SPACE_HDR10_ST2084_EXT;
        si.imageExtent=extent;si.imageArrayLayers=1;
        si.imageUsage=VK_IMAGE_USAGE_TRANSFER_DST_BIT;
        si.imageSharingMode=VK_SHARING_MODE_EXCLUSIVE;si.preTransform=caps.currentTransform;
        si.compositeAlpha=alpha;si.presentMode=VK_PRESENT_MODE_FIFO_KHR;si.clipped=VK_TRUE;
        VkResult r=vkCreateSwapchainKHR(device,&si,nullptr,&swapchain);
        if(r!=VK_SUCCESS){error="HDR10 swapchain creation: "+std::to_string(r);return false;}
        n=0;vkGetSwapchainImagesKHR(device,swapchain,&n,nullptr);
        swapImages.resize(n);vkGetSwapchainImagesKHR(device,swapchain,&n,swapImages.data());
        VkCommandPoolCreateInfo pi{};pi.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pi.queueFamilyIndex=queueFamily;pi.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        if(vkCreateCommandPool(device,&pi,nullptr,&pool)!=VK_SUCCESS){error="Command pool";return false;}
        VkCommandBufferAllocateInfo ca{};ca.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        ca.commandPool=pool;ca.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;ca.commandBufferCount=1;
        if(vkAllocateCommandBuffers(device,&ca,&cmd)!=VK_SUCCESS){error="Command buffer";return false;}
        VkSemaphoreCreateInfo sem{};sem.sType=VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
        vkCreateSemaphore(device,&sem,nullptr,&acquire);vkCreateSemaphore(device,&sem,nullptr,&render);
        prepareLut();
        ready=true;return true;
    }
    bool makeShared(uint32_t width,uint32_t height){
        if(!ready||!zeroCopySupported){error="Zero-copy Vulkan external buffer not available";return false;}
        if(shared && sharedW==width && sharedH==height && sharedImage)return true;
        releaseSharedVulkan();
        AHardwareBuffer_Desc desc{};
        desc.width=width;desc.height=height;desc.layers=1;
        desc.format=AHARDWAREBUFFER_FORMAT_R16G16B16A16_FLOAT;
        desc.usage=AHARDWAREBUFFER_USAGE_GPU_COLOR_OUTPUT|
            AHARDWAREBUFFER_USAGE_GPU_SAMPLED_IMAGE;
        if(AHardwareBuffer_allocate(&desc,&shared)!=0){
            error="Shield cannot allocate FP16 shared GPU render buffer";return false;
        }
        auto getProperties=(PFN_vkGetAndroidHardwareBufferPropertiesANDROID)
           vkGetDeviceProcAddr(device,"vkGetAndroidHardwareBufferPropertiesANDROID");
        if(!getProperties){error="Missing vkGetAndroidHardwareBufferPropertiesANDROID";return false;}
        VkAndroidHardwareBufferPropertiesANDROID properties{};
        properties.sType=VK_STRUCTURE_TYPE_ANDROID_HARDWARE_BUFFER_PROPERTIES_ANDROID;
        VkResult r=getProperties(device,shared,&properties);
        if(r!=VK_SUCCESS){error="Vulkan AHB buffer properties: "+std::to_string(r);return false;}
        VkExternalMemoryImageCreateInfo external{};
        external.sType=VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO;
        external.handleTypes=VK_EXTERNAL_MEMORY_HANDLE_TYPE_ANDROID_HARDWARE_BUFFER_BIT_ANDROID;
        VkImageCreateInfo info{};
        info.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        info.pNext=&external;
        info.imageType=VK_IMAGE_TYPE_2D;
        info.format=VK_FORMAT_R16G16B16A16_SFLOAT;
        info.extent={width,height,1};info.mipLevels=1;info.arrayLayers=1;
        info.samples=VK_SAMPLE_COUNT_1_BIT;info.tiling=VK_IMAGE_TILING_OPTIMAL;
        info.usage=VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
        info.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
        info.initialLayout=VK_IMAGE_LAYOUT_UNDEFINED;
        r=vkCreateImage(device,&info,nullptr,&sharedImage);
        if(r!=VK_SUCCESS){error="Vulkan shared FP16 image unsupported: "+std::to_string(r);return false;}
        VkMemoryRequirements req{};
        vkGetImageMemoryRequirements(device,sharedImage,&req);
        VkImportAndroidHardwareBufferInfoANDROID import{};
        import.sType=VK_STRUCTURE_TYPE_IMPORT_ANDROID_HARDWARE_BUFFER_INFO_ANDROID;
        import.buffer=shared;
        VkMemoryDedicatedAllocateInfo dedicated{};
        dedicated.sType=VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO;
        dedicated.pNext=&import;dedicated.image=sharedImage;
        VkMemoryAllocateInfo allocation{};
        allocation.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        allocation.pNext=&dedicated;
        allocation.allocationSize=properties.allocationSize;
        allocation.memoryTypeIndex=findMemory(properties.memoryTypeBits&
            req.memoryTypeBits,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        if(allocation.memoryTypeIndex==UINT32_MAX)
           allocation.memoryTypeIndex=findMemory(properties.memoryTypeBits&
               req.memoryTypeBits,0);
        if(allocation.memoryTypeIndex==UINT32_MAX){error="No Vulkan AHB-compatible memory type";return false;}
        r=vkAllocateMemory(device,&allocation,nullptr,&sharedMemory);
        if(r!=VK_SUCCESS){error="Import AHB memory: "+std::to_string(r);return false;}
        r=vkBindImageMemory(device,sharedImage,sharedMemory,0);
        if(r!=VK_SUCCESS){error="Bind imported AHB image: "+std::to_string(r);return false;}
        // Establish a persistent Vulkan layout BEFORE OpenGL imports and writes
        // the AHB. Repeated UNDEFINED->TRANSFER_SRC transitions discard frame
        // contents and can produce a black HDR surface.
        VkCommandBufferBeginInfo begin{};
        begin.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        vkResetCommandPool(device,pool,0);
        r=vkBeginCommandBuffer(cmd,&begin);
        if(r!=VK_SUCCESS){error="AHB layout command start";return false;}
        VkImageMemoryBarrier initial{};
        initial.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        initial.oldLayout=VK_IMAGE_LAYOUT_UNDEFINED;
        initial.newLayout=VK_IMAGE_LAYOUT_GENERAL;
        initial.srcAccessMask=0;
        initial.dstAccessMask=VK_ACCESS_MEMORY_READ_BIT|VK_ACCESS_MEMORY_WRITE_BIT;
        initial.srcQueueFamilyIndex=queueFamily;
        initial.dstQueueFamilyIndex=VK_QUEUE_FAMILY_EXTERNAL;
        initial.image=sharedImage;
        initial.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        initial.subresourceRange.levelCount=1;
        initial.subresourceRange.layerCount=1;
        vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
            VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,0,0,nullptr,0,nullptr,1,&initial);
        vkEndCommandBuffer(cmd);
        VkSubmitInfo submit{};
        submit.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.commandBufferCount=1;submit.pCommandBuffers=&cmd;
        r=vkQueueSubmit(queue,1,&submit,VK_NULL_HANDLE);
        if(r!=VK_SUCCESS){error="AHB initial layout submit";return false;}
        vkQueueWaitIdle(queue);
        sharedW=width;sharedH=height;return true;
    }
    bool presentShared(){
        if(!ready||!sharedImage)return false;
        uint32_t idx=0;
        VkResult r=vkAcquireNextImageKHR(device,swapchain,12000000ULL,acquire,VK_NULL_HANDLE,&idx);
        if(r==VK_TIMEOUT||r==VK_NOT_READY)return true;
        if(r!=VK_SUCCESS&&r!=VK_SUBOPTIMAL_KHR){error="Vulkan HDR acquire: "+std::to_string(r);return false;}
        vkResetCommandPool(device,pool,0);
        VkCommandBufferBeginInfo begin{};begin.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        vkBeginCommandBuffer(cmd,&begin);
        auto barrier=[&](VkImage img,VkImageLayout from,VkImageLayout to,
            VkAccessFlags src,VkAccessFlags dst,VkPipelineStageFlags ss,VkPipelineStageFlags ds){
            VkImageMemoryBarrier b{};b.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
            b.oldLayout=from;b.newLayout=to;b.srcAccessMask=src;b.dstAccessMask=dst;
            b.srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;b.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;
            b.image=img;b.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
            b.subresourceRange.levelCount=1;b.subresourceRange.layerCount=1;
            vkCmdPipelineBarrier(cmd,ss,ds,0,0,nullptr,0,nullptr,1,&b);
        };
        // OpenGL has flushed and finished writing the AHB before the call.
        // Acquire AHardwareBuffer ownership from the OpenGL ES driver.
        VkImageMemoryBarrier acquireShared{};
        acquireShared.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        acquireShared.oldLayout=VK_IMAGE_LAYOUT_GENERAL;
        acquireShared.newLayout=VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        acquireShared.srcQueueFamilyIndex=VK_QUEUE_FAMILY_EXTERNAL;
        acquireShared.dstQueueFamilyIndex=queueFamily;
        acquireShared.srcAccessMask=0;
        acquireShared.dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT;
        acquireShared.image=sharedImage;
        acquireShared.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        acquireShared.subresourceRange.levelCount=1;
        acquireShared.subresourceRange.layerCount=1;
        vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,nullptr,0,nullptr,1,&acquireShared);
        barrier(swapImages[idx],VK_IMAGE_LAYOUT_UNDEFINED,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            0,VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT);
        VkImageBlit blit{};
        blit.srcSubresource.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        blit.srcSubresource.layerCount=1;
        blit.srcOffsets[1]={int32_t(sharedW),int32_t(sharedH),1};
        blit.dstSubresource.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        blit.dstSubresource.layerCount=1;
        blit.dstOffsets[1]={int32_t(extent.width),int32_t(extent.height),1};
        vkCmdBlitImage(cmd,sharedImage,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
            swapImages[idx],VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,&blit,VK_FILTER_LINEAR);
        barrier(swapImages[idx],VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
            VK_ACCESS_TRANSFER_WRITE_BIT,0,
            VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT);
        // Preserve the imported image content across the next OpenGL frame.
        // The next GL write begins with GENERAL instead of undefined contents.
        // Release ownership back to OpenGL for the next FSRCNNX frame.
        VkImageMemoryBarrier releaseShared{};
        releaseShared.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
        releaseShared.oldLayout=VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        releaseShared.newLayout=VK_IMAGE_LAYOUT_GENERAL;
        releaseShared.srcQueueFamilyIndex=queueFamily;
        releaseShared.dstQueueFamilyIndex=VK_QUEUE_FAMILY_EXTERNAL;
        releaseShared.srcAccessMask=VK_ACCESS_TRANSFER_READ_BIT;
        releaseShared.dstAccessMask=0;
        releaseShared.image=sharedImage;
        releaseShared.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        releaseShared.subresourceRange.levelCount=1;
        releaseShared.subresourceRange.layerCount=1;
        vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,0,0,nullptr,0,nullptr,1,&releaseShared);
        vkEndCommandBuffer(cmd);
        VkPipelineStageFlags stage=VK_PIPELINE_STAGE_TRANSFER_BIT;
        VkSubmitInfo submit{};submit.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.waitSemaphoreCount=1;submit.pWaitSemaphores=&acquire;
        submit.pWaitDstStageMask=&stage;
        submit.commandBufferCount=1;submit.pCommandBuffers=&cmd;
        submit.signalSemaphoreCount=1;submit.pSignalSemaphores=&render;
        r=vkQueueSubmit(queue,1,&submit,VK_NULL_HANDLE);
        if(r!=VK_SUCCESS){error="Vulkan HDR submit: "+std::to_string(r);return false;}
        VkPresentInfoKHR present{};present.sType=VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
        present.waitSemaphoreCount=1;present.pWaitSemaphores=&render;
        present.swapchainCount=1;present.pSwapchains=&swapchain;present.pImageIndices=&idx;
        r=vkQueuePresentKHR(queue,&present);
        // Single shared buffer requires completion before next GL write.
        // No CPU pixel conversion, pixel readback or video encoding.
        vkQueueWaitIdle(queue);
        if(r!=VK_SUCCESS&&r!=VK_SUBOPTIMAL_KHR){
            error="Vulkan HDR present: "+std::to_string(r);return false;
        }
        return true;
    }
    bool resize(uint32_t width,uint32_t height){
        if(width==w&&height==h)return true;
        vkDeviceWaitIdle(device);
        if(uploadMapped){vkUnmapMemory(device,uploadMemory);uploadMapped=nullptr;}
        if(upload)vkDestroyBuffer(device,upload,nullptr);
        if(uploadMemory)vkFreeMemory(device,uploadMemory,nullptr);
        if(source)vkDestroyImage(device,source,nullptr);
        if(sourceMemory)vkFreeMemory(device,sourceMemory,nullptr);
        upload=VK_NULL_HANDLE;uploadMemory=VK_NULL_HANDLE;
        source=VK_NULL_HANDLE;sourceMemory=VK_NULL_HANDLE;
        w=width;h=height;
        VkDeviceSize bytes=(VkDeviceSize)w*h*8;
        VkBufferCreateInfo bi{};bi.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
        bi.size=bytes;bi.usage=VK_BUFFER_USAGE_TRANSFER_SRC_BIT;bi.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
        if(vkCreateBuffer(device,&bi,nullptr,&upload)!=VK_SUCCESS){error="Staging buffer";return false;}
        VkMemoryRequirements req{};vkGetBufferMemoryRequirements(device,upload,&req);
        VkMemoryAllocateInfo mi{};mi.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
        mi.allocationSize=req.size;mi.memoryTypeIndex=findMemory(req.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        if(mi.memoryTypeIndex==UINT32_MAX){error="No coherent Vulkan upload memory";return false;}
        if(vkAllocateMemory(device,&mi,nullptr,&uploadMemory)!=VK_SUCCESS){error="Upload allocation";return false;}
        vkBindBufferMemory(device,upload,uploadMemory,0);
        if(vkMapMemory(device,uploadMemory,0,bytes,0,&uploadMapped)!=VK_SUCCESS){error="Upload mapping";return false;}
        VkImageCreateInfo ii{};ii.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
        ii.imageType=VK_IMAGE_TYPE_2D;ii.format=format;
        ii.extent={w,h,1};ii.mipLevels=1;ii.arrayLayers=1;
        ii.samples=VK_SAMPLE_COUNT_1_BIT;ii.tiling=VK_IMAGE_TILING_OPTIMAL;
        ii.usage=VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
        ii.sharingMode=VK_SHARING_MODE_EXCLUSIVE;ii.initialLayout=VK_IMAGE_LAYOUT_UNDEFINED;
        if(vkCreateImage(device,&ii,nullptr,&source)!=VK_SUCCESS){error="FP16 image";return false;}
        vkGetImageMemoryRequirements(device,source,&req);
        mi.allocationSize=req.size;
        mi.memoryTypeIndex=findMemory(req.memoryTypeBits,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        if(mi.memoryTypeIndex==UINT32_MAX){error="No device-local Vulkan image memory";return false;}
        if(vkAllocateMemory(device,&mi,nullptr,&sourceMemory)!=VK_SUCCESS){error="Source allocation";return false;}
        vkBindImageMemory(device,source,sourceMemory,0);
        return true;
    }
    bool frame(const uint8_t* rgba,uint32_t width,uint32_t height){
        std::lock_guard<std::mutex> lock(guard);
        if(!ready || !rgba || !width || !height)return false;
        if(!resize(width,height)){ready=false;LOG("%s",error.c_str());return false;}
        // FP16 PQ colour values are already display-referred. Avoid CPU pow()
        // per pixel by using precomputed 8-bit decode and 16-bit PQ lookup.
        uint16_t* dst=(uint16_t*)uploadMapped;
        for(uint32_t y=0;y<h;y++){
            const uint8_t* src=rgba+((size_t)(h-1-y)*w*4);
            for(uint32_t x=0;x<w;x++){
                float r=gamma[src[0]],g=gamma[src[1]],b=gamma[src[2]];
                float rr=0.627404f*r+0.329282f*g+0.043314f*b;
                float gg=0.069097f*r+0.919540f*g+0.011362f*b;
                float bb=0.016391f*r+0.088013f*g+0.895595f*b;
                auto idx=[](float v)->uint16_t{return (uint16_t)(std::min(1.f,std::max(0.f,v))*65535.f);};
                size_t at=((size_t)y*w+x)*4;
                dst[at]=pq[idx(rr)];dst[at+1]=pq[idx(gg)];dst[at+2]=pq[idx(bb)];
                dst[at+3]=0x3c00;src+=4;
            }
        }
        uint32_t imageIndex=0;
        VkResult r=vkAcquireNextImageKHR(device,swapchain,16000000ULL,acquire,VK_NULL_HANDLE,&imageIndex);
        // A display refresh-rate switch can destroy/recreate the Android
        // window. Never hold the native mutex forever in acquire: the surface
        // lifecycle must be able to stop and recreate this swapchain.
        if(r==VK_TIMEOUT || r==VK_NOT_READY) return true; // drop this frame
        if(r!=VK_SUCCESS && r!=VK_SUBOPTIMAL_KHR){LOG("Acquire: %d",r);return false;}
        vkResetCommandPool(device,pool,0);
        VkCommandBufferBeginInfo bi{};bi.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        vkBeginCommandBuffer(cmd,&bi);
        auto barrier=[&](VkImage image,VkImageLayout oldLayout,VkImageLayout newLayout,
                         VkAccessFlags src,VkAccessFlags dst,VkPipelineStageFlags srcStage,
                         VkPipelineStageFlags dstStage){
            VkImageMemoryBarrier b{};b.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
            b.oldLayout=oldLayout;b.newLayout=newLayout;
            b.srcAccessMask=src;b.dstAccessMask=dst;
            b.srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;
            b.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED;b.image=image;
            b.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
            b.subresourceRange.levelCount=1;b.subresourceRange.layerCount=1;
            vkCmdPipelineBarrier(cmd,srcStage,dstStage,0,0,nullptr,0,nullptr,1,&b);
        };
        barrier(source,VK_IMAGE_LAYOUT_UNDEFINED,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,0,
            VK_ACCESS_TRANSFER_WRITE_BIT,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT);
        VkBufferImageCopy copy{};copy.imageSubresource.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        copy.imageSubresource.layerCount=1;copy.imageExtent={w,h,1};
        vkCmdCopyBufferToImage(cmd,upload,source,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,&copy);
        barrier(source,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
            VK_ACCESS_TRANSFER_WRITE_BIT,VK_ACCESS_TRANSFER_READ_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT);
        barrier(swapImages[imageIndex],VK_IMAGE_LAYOUT_UNDEFINED,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            0,VK_ACCESS_TRANSFER_WRITE_BIT,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT);
        VkImageBlit blit{};
        blit.srcSubresource.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        blit.srcSubresource.layerCount=1;blit.srcOffsets[1]={int32_t(w),int32_t(h),1};
        blit.dstSubresource.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
        blit.dstSubresource.layerCount=1;
        blit.dstOffsets[1]={int32_t(extent.width),int32_t(extent.height),1};
        vkCmdBlitImage(cmd,source,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
            swapImages[imageIndex],VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,&blit,VK_FILTER_LINEAR);
        barrier(swapImages[imageIndex],VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
            VK_ACCESS_TRANSFER_WRITE_BIT,0,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT);
        vkEndCommandBuffer(cmd);
        VkPipelineStageFlags stage=VK_PIPELINE_STAGE_TRANSFER_BIT;
        VkSubmitInfo submit{};submit.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.waitSemaphoreCount=1;submit.pWaitSemaphores=&acquire;
        submit.pWaitDstStageMask=&stage;submit.commandBufferCount=1;submit.pCommandBuffers=&cmd;
        submit.signalSemaphoreCount=1;submit.pSignalSemaphores=&render;
        r=vkQueueSubmit(queue,1,&submit,VK_NULL_HANDLE);
        if(r!=VK_SUCCESS){LOG("Submit: %d",r);return false;}
        VkPresentInfoKHR present{};present.sType=VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
        present.waitSemaphoreCount=1;present.pWaitSemaphores=&render;
        present.swapchainCount=1;present.pSwapchains=&swapchain;present.pImageIndices=&imageIndex;
        r=vkQueuePresentKHR(queue,&present);
        vkQueueWaitIdle(queue);
        if(r!=VK_SUCCESS && r!=VK_SUBOPTIMAL_KHR){LOG("Present: %d",r);return false;}
        return true;
    }
};
static HdrBridge bridge;
extern "C" JNIEXPORT jstring JNICALL
Java_com_example_liteplayer_VulkanHdrBridgeView_nativeStart(JNIEnv* env,jobject,jobject surface){
    std::lock_guard<std::mutex> lock(bridge.guard);
    bridge.destroy();
    if(!bridge.initialize(env,surface)){
        std::string msg=bridge.error;
        bridge.destroy();
        return env->NewStringUTF(msg.c_str());
    }
    return env->NewStringUTF("");
}
extern "C" JNIEXPORT jboolean JNICALL
Java_com_example_liteplayer_VulkanHdrBridgeView_nativeFrame(JNIEnv* env,jobject,jobject data,jint width,jint height){
    const auto* ptr=(const uint8_t*)env->GetDirectBufferAddress(data);
    return bridge.frame(ptr,(uint32_t)width,(uint32_t)height)?JNI_TRUE:JNI_FALSE;
}
extern "C" JNIEXPORT void JNICALL
Java_com_example_liteplayer_VulkanHdrBridgeView_nativeStop(JNIEnv*,jobject){
    std::lock_guard<std::mutex> lock(bridge.guard);
    bridge.destroy();
}

static std::mutex interopGlMutex;
// All GL/EGL calls are made on ReferenceScalerView's GL thread.
extern "C" JNIEXPORT jint JNICALL
Java_com_example_liteplayer_VulkanHdrBridgeView_nativePrepareShared(JNIEnv* env,jobject,jint width,jint height){
    std::lock_guard<std::mutex> lock(bridge.guard);
    if(!bridge.ready||width<=0||height<=0)return 0;
    // The surface is normally allocated once. When changing resolution the
    // caller must release the old GL attachment first.
    if(!bridge.makeShared((uint32_t)width,(uint32_t)height)) {
        LOG("AHB zero-copy: %s",bridge.error.c_str());return 0;
    }
    auto getNative=(PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC)
        eglGetProcAddress("eglGetNativeClientBufferANDROID");
    auto createImage=(PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
    auto targetImage=(PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)
        eglGetProcAddress("glEGLImageTargetTexture2DOES");
    if(!getNative||!createImage||!targetImage){
        bridge.error="Missing EGL native AHardwareBuffer image interop";
        return 0;
    }
    bridge.eglDisplay=eglGetCurrentDisplay();
    EGLClientBuffer client=getNative(bridge.shared);
    const EGLint attrs[]={EGL_IMAGE_PRESERVED_KHR,EGL_TRUE,EGL_NONE};
    bridge.eglImage=createImage(bridge.eglDisplay,EGL_NO_CONTEXT,
        EGL_NATIVE_BUFFER_ANDROID,client,attrs);
    if(bridge.eglImage==EGL_NO_IMAGE_KHR){
        bridge.error="EGL cannot import the shared FP16 AHardwareBuffer";return 0;
    }
    glGenTextures(1,&bridge.glTexture);
    glBindTexture(GL_TEXTURE_2D,bridge.glTexture);
    targetImage(GL_TEXTURE_2D,bridge.eglImage);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    glGenFramebuffers(1,&bridge.glFramebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER,bridge.glFramebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
        bridge.glTexture,0);
    GLenum status=glCheckFramebufferStatus(GL_FRAMEBUFFER);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    if(status!=GL_FRAMEBUFFER_COMPLETE){
        bridge.error="EGL FP16 shared render framebuffer incomplete: "+
            std::to_string(status);return 0;
    }
    return (jint)bridge.glFramebuffer;
}
extern "C" JNIEXPORT jboolean JNICALL
Java_com_example_liteplayer_VulkanHdrBridgeView_nativePresentShared(JNIEnv*,jobject){
    std::lock_guard<std::mutex> lock(bridge.guard);
    if(!bridge.ready||!bridge.sharedImage)return JNI_FALSE;
    bool success=bridge.presentShared();
    if(!success)LOG("AHB present failed: %s",bridge.error.c_str());
    return success?JNI_TRUE:JNI_FALSE;
}
extern "C" JNIEXPORT jstring JNICALL
Java_com_example_liteplayer_VulkanHdrBridgeView_nativeSharedError(JNIEnv* env,jobject){
    std::lock_guard<std::mutex> lock(bridge.guard);
    return env->NewStringUTF(bridge.error.c_str());
}
extern "C" JNIEXPORT void JNICALL
Java_com_example_liteplayer_VulkanHdrBridgeView_nativeReleaseSharedGL(JNIEnv*,jobject){
    std::lock_guard<std::mutex> lock(bridge.guard);
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    if(bridge.glFramebuffer)glDeleteFramebuffers(1,&bridge.glFramebuffer);
    if(bridge.glTexture)glDeleteTextures(1,&bridge.glTexture);
    auto destroyImage=(PFNEGLDESTROYIMAGEKHRPROC)eglGetProcAddress("eglDestroyImageKHR");
    if(destroyImage&&bridge.eglImage!=EGL_NO_IMAGE_KHR)
        destroyImage(bridge.eglDisplay,bridge.eglImage);
    bridge.glFramebuffer=0;bridge.glTexture=0;bridge.eglImage=EGL_NO_IMAGE_KHR;
    bridge.eglDisplay=EGL_NO_DISPLAY;
}
