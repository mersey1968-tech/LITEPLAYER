#define VK_USE_PLATFORM_ANDROID_KHR 1
#include <vulkan/vulkan.h>
#include <android/native_window_jni.h>
#include <jni.h>
#include <sstream>
#include <vector>
#include <cstring>
#include <unistd.h>

static const char* resultName(VkResult r) {
    switch(r) {
        case VK_SUCCESS:return "VK_SUCCESS";
        case VK_ERROR_EXTENSION_NOT_PRESENT:return "VK_ERROR_EXTENSION_NOT_PRESENT";
        case VK_ERROR_FORMAT_NOT_SUPPORTED:return "VK_ERROR_FORMAT_NOT_SUPPORTED";
        case VK_ERROR_INITIALIZATION_FAILED:return "VK_ERROR_INITIALIZATION_FAILED";
        case VK_ERROR_SURFACE_LOST_KHR:return "VK_ERROR_SURFACE_LOST_KHR";
        case VK_ERROR_OUT_OF_DATE_KHR:return "VK_ERROR_OUT_OF_DATE_KHR";
        default:return "other VkResult";
    }
}
static bool hasExt(const std::vector<VkExtensionProperties>& list, const char* name) {
    for(auto& x:list) if(strcmp(x.extensionName,name)==0)return true;
    return false;
}
extern "C" JNIEXPORT jstring JNICALL
Java_com_example_liteplayer_VulkanHdrProbeActivity_nativeProbe(JNIEnv* env, jobject, jobject javaSurface) {
    std::ostringstream log;
    ANativeWindow* window = ANativeWindow_fromSurface(env, javaSurface);
    if (!window) return env->NewStringUTF("No native Android window");
    VkInstance instance=VK_NULL_HANDLE;
    VkSurfaceKHR surface=VK_NULL_HANDLE;
    VkDevice device=VK_NULL_HANDLE;
    VkSwapchainKHR swapchain=VK_NULL_HANDLE;
    VkRenderPass renderPass=VK_NULL_HANDLE;
    VkCommandPool commandPool=VK_NULL_HANDLE;
    VkSemaphore available=VK_NULL_HANDLE, rendered=VK_NULL_HANDLE;
    VkFence fence=VK_NULL_HANDLE;
    std::vector<VkFramebuffer> framebuffers;
    std::vector<VkImageView> views;
    auto cleanup=[&] {
        if(device) {
            vkDeviceWaitIdle(device);
            if(fence) vkDestroyFence(device,fence,nullptr);
            if(available) vkDestroySemaphore(device,available,nullptr);
            if(rendered) vkDestroySemaphore(device,rendered,nullptr);
            if(commandPool) vkDestroyCommandPool(device,commandPool,nullptr);
            for(auto x:framebuffers)vkDestroyFramebuffer(device,x,nullptr);
            for(auto x:views)vkDestroyImageView(device,x,nullptr);
            if(renderPass)vkDestroyRenderPass(device,renderPass,nullptr);
            if(swapchain)vkDestroySwapchainKHR(device,swapchain,nullptr);
            vkDestroyDevice(device,nullptr);
        }
        if(surface && instance)vkDestroySurfaceKHR(instance,surface,nullptr);
        if(instance)vkDestroyInstance(instance,nullptr);
        ANativeWindow_release(window);
    };
    do {
        uint32_t extCount=0;
        VkResult r=vkEnumerateInstanceExtensionProperties(nullptr,&extCount,nullptr);
        if(r!=VK_SUCCESS){log<<"Vulkan instance extension enumeration failed: "<<r;break;}
        std::vector<VkExtensionProperties> exts(extCount);
        vkEnumerateInstanceExtensionProperties(nullptr,&extCount,exts.data());
        bool android=hasExt(exts,VK_KHR_ANDROID_SURFACE_EXTENSION_NAME);
        bool colorspace=hasExt(exts,VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME);
        log<<"Vulkan android_surface: "<<(android?"yes":"no")
           <<"\nVK_EXT_swapchain_colorspace: "<<(colorspace?"yes":"no");
        if(!android){log<<"\nCannot create Vulkan Android surface";break;}
        std::vector<const char*> enabled={VK_KHR_SURFACE_EXTENSION_NAME,VK_KHR_ANDROID_SURFACE_EXTENSION_NAME};
        if(colorspace)enabled.push_back(VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME);
        VkApplicationInfo app={};
        app.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO;
        app.pApplicationName="Reflite HDR10 Capability Probe";
        app.apiVersion=VK_API_VERSION_1_0;
        VkInstanceCreateInfo ic={};
        ic.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        ic.pApplicationInfo=&app;
        ic.enabledExtensionCount=(uint32_t)enabled.size();
        ic.ppEnabledExtensionNames=enabled.data();
        r=vkCreateInstance(&ic,nullptr,&instance);
        if(r!=VK_SUCCESS){log<<"\nvkCreateInstance: "<<r;break;}
        VkAndroidSurfaceCreateInfoKHR sci={};
        sci.sType=VK_STRUCTURE_TYPE_ANDROID_SURFACE_CREATE_INFO_KHR;
        sci.window=window;
        r=vkCreateAndroidSurfaceKHR(instance,&sci,nullptr,&surface);
        if(r!=VK_SUCCESS){log<<"\nvkCreateAndroidSurfaceKHR: "<<r;break;}
        uint32_t gpuCount=0;
        r=vkEnumeratePhysicalDevices(instance,&gpuCount,nullptr);
        if(r!=VK_SUCCESS || !gpuCount){log<<"\nNo Vulkan physical device";break;}
        std::vector<VkPhysicalDevice> gpus(gpuCount);
        vkEnumeratePhysicalDevices(instance,&gpuCount,gpus.data());
        VkPhysicalDevice gpu=VK_NULL_HANDLE;
        uint32_t family=0;
        for(auto candidate:gpus){
            uint32_t qCount=0;
            vkGetPhysicalDeviceQueueFamilyProperties(candidate,&qCount,nullptr);
            std::vector<VkQueueFamilyProperties> qs(qCount);
            vkGetPhysicalDeviceQueueFamilyProperties(candidate,&qCount,qs.data());
            uint32_t devCount=0;
            vkEnumerateDeviceExtensionProperties(candidate,nullptr,&devCount,nullptr);
            std::vector<VkExtensionProperties> ds(devCount);
            vkEnumerateDeviceExtensionProperties(candidate,nullptr,&devCount,ds.data());
            if(!hasExt(ds,VK_KHR_SWAPCHAIN_EXTENSION_NAME)) continue;
            for(uint32_t q=0;q<qCount;q++){
                VkBool32 supported=VK_FALSE;
                vkGetPhysicalDeviceSurfaceSupportKHR(candidate,q,surface,&supported);
                if(supported && (qs[q].queueFlags & VK_QUEUE_GRAPHICS_BIT)){gpu=candidate;family=q;break;}
            }
            if(gpu)break;
        }
        if(!gpu){log<<"\nNo swapchain-capable GPU / present queue";break;}
        VkPhysicalDeviceProperties props={};
        vkGetPhysicalDeviceProperties(gpu,&props);
        log<<"\nGPU: "<<props.deviceName;
        uint32_t nFormats=0;
        r=vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&nFormats,nullptr);
        if(r!=VK_SUCCESS || !nFormats){log<<"\nNo surface formats: "<<r;break;}
        std::vector<VkSurfaceFormatKHR> formats(nFormats);
        vkGetPhysicalDeviceSurfaceFormatsKHR(gpu,surface,&nFormats,formats.data());
        log<<"\nSurface format/colour-space pairs: "<<nFormats;
        VkSurfaceFormatKHR chosen={};
        bool hdr=false;
        for(auto f:formats) {
            if(f.colorSpace==VK_COLOR_SPACE_HDR10_ST2084_EXT){
                log<<"\nHDR10 ST2084 reported, VkFormat="<<f.format;
                if(!hdr) {
                    if(f.format==VK_FORMAT_A2B10G10R10_UNORM_PACK32 ||
                       f.format==VK_FORMAT_A2R10G10B10_UNORM_PACK32 ||
                       f.format==VK_FORMAT_R16G16B16A16_SFLOAT) {
                        chosen=f;hdr=true;
                    }
                }
            }
        }
        if(!hdr){
            log<<"\nRESULT: no usable HDR10 ST2084 swapchain format";
            log<<"\nThis does NOT affect normal video HDR passthrough.";
            break;
        }
        log<<"\nSelected HDR10 VkFormat: "<<chosen.format;
        float priority=1.0f;
        VkDeviceQueueCreateInfo qci={};
        qci.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        qci.queueFamilyIndex=family;qci.queueCount=1;qci.pQueuePriorities=&priority;
        const char* devExt=VK_KHR_SWAPCHAIN_EXTENSION_NAME;
        VkDeviceCreateInfo dci={};
        dci.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        dci.queueCreateInfoCount=1;dci.pQueueCreateInfos=&qci;
        dci.enabledExtensionCount=1;dci.ppEnabledExtensionNames=&devExt;
        r=vkCreateDevice(gpu,&dci,nullptr,&device);
        if(r!=VK_SUCCESS){log<<"\nvkCreateDevice failed: "<<r;break;}
        VkSurfaceCapabilitiesKHR caps={};
        r=vkGetPhysicalDeviceSurfaceCapabilitiesKHR(gpu,surface,&caps);
        if(r!=VK_SUCCESS){log<<"\nSurface capabilities failed: "<<r;break;}
        VkExtent2D extent=caps.currentExtent;
        if(extent.width==UINT32_MAX){
            extent.width=(uint32_t)ANativeWindow_getWidth(window);
            extent.height=(uint32_t)ANativeWindow_getHeight(window);
            if(extent.width<caps.minImageExtent.width)extent.width=caps.minImageExtent.width;
            if(extent.height<caps.minImageExtent.height)extent.height=caps.minImageExtent.height;
            if(extent.width>caps.maxImageExtent.width)extent.width=caps.maxImageExtent.width;
            if(extent.height>caps.maxImageExtent.height)extent.height=caps.maxImageExtent.height;
        }
        VkCompositeAlphaFlagBitsKHR alpha=VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
        if(!(caps.supportedCompositeAlpha & alpha)){
            alpha=VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR;
            for(int bit=0;bit<4;bit++) if(caps.supportedCompositeAlpha & (1<<bit)) {
                alpha=(VkCompositeAlphaFlagBitsKHR)(1<<bit);break;
            }
        }
        if(!(caps.supportedUsageFlags & VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT)){
            log<<"\nHDR10 format does not support colour attachment";break;
        }
        VkSwapchainCreateInfoKHR sc={};
        sc.sType=VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
        sc.surface=surface;
        sc.minImageCount=caps.minImageCount+1;
        if(caps.maxImageCount && sc.minImageCount>caps.maxImageCount)sc.minImageCount=caps.maxImageCount;
        sc.imageFormat=chosen.format;sc.imageColorSpace=chosen.colorSpace;
        sc.imageExtent=extent;sc.imageArrayLayers=1;
        sc.imageUsage=VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
        sc.imageSharingMode=VK_SHARING_MODE_EXCLUSIVE;
        sc.preTransform=caps.currentTransform;
        sc.compositeAlpha=alpha;sc.presentMode=VK_PRESENT_MODE_FIFO_KHR;
        sc.clipped=VK_TRUE;
        r=vkCreateSwapchainKHR(device,&sc,nullptr,&swapchain);
        log<<"\nvkCreateSwapchainKHR: "<<resultName(r)<<" ("<<r<<")";
        if(r!=VK_SUCCESS)break;
        uint32_t count=0;
        vkGetSwapchainImagesKHR(device,swapchain,&count,nullptr);
        std::vector<VkImage> images(count);
        vkGetSwapchainImagesKHR(device,swapchain,&count,images.data());
        for(VkImage img:images){
            VkImageViewCreateInfo vi={};
            vi.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
            vi.image=img;vi.viewType=VK_IMAGE_VIEW_TYPE_2D;vi.format=chosen.format;
            vi.components={VK_COMPONENT_SWIZZLE_IDENTITY,VK_COMPONENT_SWIZZLE_IDENTITY,
                VK_COMPONENT_SWIZZLE_IDENTITY,VK_COMPONENT_SWIZZLE_IDENTITY};
            vi.subresourceRange.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;
            vi.subresourceRange.levelCount=1;vi.subresourceRange.layerCount=1;
            VkImageView view=VK_NULL_HANDLE;
            r=vkCreateImageView(device,&vi,nullptr,&view);
            if(r!=VK_SUCCESS)break;
            views.push_back(view);
        }
        if(views.size()!=images.size()){log<<"\nImage view creation failed";break;}
        VkAttachmentDescription attachment={};
        attachment.format=chosen.format;attachment.samples=VK_SAMPLE_COUNT_1_BIT;
        attachment.loadOp=VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachment.storeOp=VK_ATTACHMENT_STORE_OP_STORE;
        attachment.initialLayout=VK_IMAGE_LAYOUT_UNDEFINED;
        attachment.finalLayout=VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        VkAttachmentReference aref={0,VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
        VkSubpassDescription sub={};
        sub.pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS;
        sub.colorAttachmentCount=1;sub.pColorAttachments=&aref;
        VkRenderPassCreateInfo rp={};
        rp.sType=VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
        rp.attachmentCount=1;rp.pAttachments=&attachment;
        rp.subpassCount=1;rp.pSubpasses=&sub;
        r=vkCreateRenderPass(device,&rp,nullptr,&renderPass);
        if(r!=VK_SUCCESS){log<<"\nRender pass creation failed: "<<r;break;}
        for(auto view:views){
            VkFramebufferCreateInfo fi={};
            fi.sType=VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
            fi.renderPass=renderPass;fi.attachmentCount=1;fi.pAttachments=&view;
            fi.width=extent.width;fi.height=extent.height;fi.layers=1;
            VkFramebuffer fb=VK_NULL_HANDLE;
            r=vkCreateFramebuffer(device,&fi,nullptr,&fb);
            if(r!=VK_SUCCESS)break;
            framebuffers.push_back(fb);
        }
        if(framebuffers.size()!=images.size()){log<<"\nFramebuffer creation failed";break;}
        VkCommandPoolCreateInfo pci={};
        pci.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
        pci.queueFamilyIndex=family;
        r=vkCreateCommandPool(device,&pci,nullptr,&commandPool);
        if(r!=VK_SUCCESS){log<<"\nCommand pool failed";break;}
        VkCommandBuffer cmd=VK_NULL_HANDLE;
        VkCommandBufferAllocateInfo cai={};
        cai.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
        cai.commandPool=commandPool;cai.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY;cai.commandBufferCount=1;
        r=vkAllocateCommandBuffers(device,&cai,&cmd);
        if(r!=VK_SUCCESS){log<<"\nCommand buffer allocation failed";break;}
        VkSemaphoreCreateInfo si={};si.sType=VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;
        vkCreateSemaphore(device,&si,nullptr,&available);
        vkCreateSemaphore(device,&si,nullptr,&rendered);
        VkFenceCreateInfo fci={};fci.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
        vkCreateFence(device,&fci,nullptr,&fence);
        uint32_t imageIndex=0;
        r=vkAcquireNextImageKHR(device,swapchain,UINT64_MAX,available,VK_NULL_HANDLE,&imageIndex);
        if(r!=VK_SUCCESS && r!=VK_SUBOPTIMAL_KHR){log<<"\nAcquire failed: "<<r;break;}
        VkCommandBufferBeginInfo bi={};bi.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
        vkBeginCommandBuffer(cmd,&bi);
        VkClearValue clear={};clear.color.float32[0]=0.55f;clear.color.float32[1]=0.30f;
        clear.color.float32[2]=0.12f;clear.color.float32[3]=1.f;
        VkRenderPassBeginInfo rbi={};
        rbi.sType=VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
        rbi.renderPass=renderPass;rbi.framebuffer=framebuffers[imageIndex];
        rbi.renderArea.extent=extent;rbi.clearValueCount=1;rbi.pClearValues=&clear;
        vkCmdBeginRenderPass(cmd,&rbi,VK_SUBPASS_CONTENTS_INLINE);
        vkCmdEndRenderPass(cmd);vkEndCommandBuffer(cmd);
        VkPipelineStageFlags stage=VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
        VkSubmitInfo submit={};submit.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO;
        submit.waitSemaphoreCount=1;submit.pWaitSemaphores=&available;
        submit.pWaitDstStageMask=&stage;
        submit.commandBufferCount=1;submit.pCommandBuffers=&cmd;
        submit.signalSemaphoreCount=1;submit.pSignalSemaphores=&rendered;
        VkQueue queue=VK_NULL_HANDLE;vkGetDeviceQueue(device,family,0,&queue);
        r=vkQueueSubmit(queue,1,&submit,fence);
        if(r!=VK_SUCCESS){log<<"\nSubmit failed: "<<r;break;}
        VkPresentInfoKHR present={};present.sType=VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
        present.waitSemaphoreCount=1;present.pWaitSemaphores=&rendered;
        present.swapchainCount=1;present.pSwapchains=&swapchain;present.pImageIndices=&imageIndex;
        r=vkQueuePresentKHR(queue,&present);
        log<<"\nvkQueuePresentKHR: "<<resultName(r)<<" ("<<r<<")";
        if(r==VK_SUCCESS || r==VK_SUBOPTIMAL_KHR){
            log<<"\nRESULT: HDR10 PRESENTATION SUBMITTED. Check TV HDR mode.";
            // Keep the test colour on-screen for the TV to recognize HDR10.
            sleep(8);
        }
    } while(false);
    cleanup();
    return env->NewStringUTF(log.str().c_str());
}
