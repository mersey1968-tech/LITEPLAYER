from pathlib import Path
import re
root=Path("proj/app/src/main/java/com/example/liteplayer")
p=root/"FsrcnnxPipeline.kt"
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)
# Dedicated source-resolution Y and chroma targets, resolved once per frame.
once("    private var composite=0", """    private var composite=0
    private var splitProgram=0
    private var splitFbo=0
    private var sourceY=0
    private var sourceUV=0
    private var splitW=0
    private var splitH=0
    private fun releaseSplit() {
        if(splitFbo!=0) GLES30.glDeleteFramebuffers(1,intArrayOf(splitFbo),0)
        if(sourceY!=0) GLES30.glDeleteTextures(1,intArrayOf(sourceY,sourceUV),0)
        splitFbo=0;sourceY=0;sourceUV=0;splitW=0;splitH=0
    }
    private fun ensureSplit(w:Int,h:Int) {
        if(splitW==w && splitH==h && splitFbo!=0)return
        releaseSplit()
        val ids=IntArray(2)
        GLES30.glGenTextures(2,ids,0)
        sourceY=ids[0];sourceUV=ids[1]
        for(i in 0..1) {
            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,ids[i])
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MIN_FILTER,GLES30.GL_NEAREST)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MAG_FILTER,GLES30.GL_NEAREST)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_WRAP_S,GLES30.GL_CLAMP_TO_EDGE)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_WRAP_T,GLES30.GL_CLAMP_TO_EDGE)
            GLES30.glTexImage2D(GLES30.GL_TEXTURE_2D,0,if(i==0)GLES30.GL_R16F else GLES30.GL_RG16F,w,h,0,if(i==0)GLES30.GL_RED else GLES30.GL_RG,GLES30.GL_HALF_FLOAT,null)
        }
        GLES30.glGenFramebuffers(1,ids,0);splitFbo=ids[0]
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,splitFbo)
        GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER,GLES30.GL_COLOR_ATTACHMENT0,GLES30.GL_TEXTURE_2D,sourceY,0)
        GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER,GLES30.GL_COLOR_ATTACHMENT0+1,GLES30.GL_TEXTURE_2D,sourceUV,0)
        GLES30.glDrawBuffers(2,intArrayOf(GLES30.GL_COLOR_ATTACHMENT0,GLES30.GL_COLOR_ATTACHMENT0+1),0)
        check(GLES30.glCheckFramebufferStatus(GLES30.GL_FRAMEBUFFER)==GLES30.GL_FRAMEBUFFER_COMPLETE)
        splitW=w;splitH=h
    }
    private fun splitFrame(video:Int,matrix:FloatArray,w:Int,h:Int) {
        ensureSplit(w,h)
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,splitFbo)
        GLES30.glViewport(0,0,w,h)
        GLES30.glUseProgram(splitProgram)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES,video)
        setUniform1i(splitProgram,"uVideo",0)
        uploadMatrix(splitProgram,uniformLocation(splitProgram,"uMatrix"),matrix)
        draw(splitProgram)
    }
""")
# The neural sampler definitions use an ordinary texture, never OES.
a=s.index('                    defs.append("uniform samplerExternalOES u_LUMA;')
b=s.index('                } else {',a)
s=s[:a]+'''                    defs.append("uniform mediump sampler2D u_LUMA;\\n")
                    defs.append("float LUMA_texOff(highp vec2 d){return texture(u_LUMA,uv+d/uSize).r;}\\n")
                    defs.append("float LUMA_texOff(int n){return texture(u_LUMA,uv).r;}\\n")
'''+s[b:]
s=s.replace('if(binds.contains("LUMA"))"#extension GL_OES_EGL_image_external_essl3 : require\\n" else ""','""')
s=s.replace('precision highp float;in vec2 uv;out vec4 outputColor;uniform vec2 uSize;', 'precision mediump float;in highp vec2 uv;out vec4 outputColor;uniform highp vec2 uSize;')
s=s.replace('_texOff(vec2 d)', '_texOff(highp vec2 d)').replace('_tex(vec2 p)', '_tex(highp vec2 p)')
s=s.replace('uniform sampler2D u_', 'uniform mediump sampler2D u_')
s=s.replace('vec2 fcoord = fract(', 'highp vec2 fcoord = fract(').replace('vec2 base = SUBCONV1_pos', 'highp vec2 base = SUBCONV1_pos')
# The aggregation body is loaded from the asset at runtime.
s=s.replace('section.substringAfter("vec4 hook()")','section.substringAfter("vec4 hook()").replace("vec2 fcoord", "highp vec2 fcoord").replace("vec2 base", "highp vec2 base")')
# Replace the accumulated image-processing compositor completely.
a=s.index('        val compositeSource="""')
b=s.index('        prepareGeometry()',a)
s=s[:a]+'''        splitProgram=link(vertexShader,"""#version 300 es
            #extension GL_OES_EGL_image_external_essl3 : require
            precision mediump float;
            in highp vec2 uv;
            uniform highp mat4 uMatrix;
            uniform mediump samplerExternalOES uVideo;
            layout(location=0) out vec4 yOut;
            layout(location=1) out vec4 uvOut;
            void main(){
                vec3 rgb=texture(uVideo,(uMatrix*vec4(uv,0.,1.)).xy).rgb;
                float y=dot(rgb,vec3(.2126,.7152,.0722));
                yOut=vec4(y,0.,0.,1.);
                uvOut=vec4((rgb.b-y)/1.8556,(rgb.r-y)/1.5748,0.,1.);
            }
        """)
        composite=link(vertexShader,"""#version 300 es
            precision mediump float;
            in highp vec2 uv;
            uniform mediump sampler2D uNeural;
            uniform mediump sampler2D uChroma;
            uniform highp vec2 uNeuralSize;
            uniform highp vec2 uChromaSize;
            uniform float uNeedsScale;
            uniform float uDitherStep;
            out vec4 outColor;
            // Lanczos2, separable four-tap kernel. No cubic interpolation.
            float sinc(float x) {
                float a=abs(x);
                if(a<.001)return 1.;
                float p=3.14159265*x;
                return sin(p)/p;
            }
            vec4 weights(float f) {
                vec4 x=vec4(1.+f,f,1.-f,2.-f);
                vec4 w=vec4(sinc(x.x)*sinc(x.x*.5),sinc(x.y)*sinc(x.y*.5),
                            sinc(x.z)*sinc(x.z*.5),sinc(x.w)*sinc(x.w*.5));
                return w/dot(w,vec4(1.));
            }
            float lumaAt(highp vec2 pos) {
                highp vec2 px=pos*uNeuralSize-.5;
                ivec2 b=ivec2(floor(px)), limit=ivec2(uNeuralSize)-1;
                vec4 wx=weights(fract(px.x)), wy=weights(fract(px.y));
                float sum=0.,lo=1.,hi=0.;
                for(int j=0;j<4;j++)for(int i=0;i<4;i++){
                    float v=texelFetch(uNeural,clamp(b+ivec2(i-1,j-1),ivec2(0),limit),0).r;
                    sum+=wx[i]*wy[j]*v;
                    if(i>=1 && i<=2 && j>=1 && j<=2){lo=min(lo,v);hi=max(hi,v);}
                }
                return clamp(sum,lo,hi);
            }
            vec2 chromaAt(highp vec2 pos) {
                highp vec2 px=pos*uChromaSize-.5;
                ivec2 b=ivec2(floor(px)),limit=ivec2(uChromaSize)-1;
                vec4 wx=weights(fract(px.x)),wy=weights(fract(px.y));
                vec2 sum=vec2(0.),lo=vec2(1.),hi=vec2(-1.);
                for(int j=0;j<4;j++)for(int i=0;i<4;i++){
                    vec2 v=texelFetch(uChroma,clamp(b+ivec2(i-1,j-1),ivec2(0),limit),0).rg;
                    sum+=wx[i]*wy[j]*v;
                    if(i>=1 && i<=2 && j>=1 && j<=2){lo=min(lo,v);hi=max(hi,v);}
                }
                return clamp(sum,lo,hi);
            }
            // Two independent integer hashes produce spatial TPDF dither.
            uint hash32(uint n) {
                n ^= n >> 16u; n *= 0x7feb352du;
                n ^= n >> 15u; n *= 0x846ca68bu; return n^(n>>16u);
            }
            void main(){
                float y=uNeedsScale>.5?lumaAt(uv):texture(uNeural,uv).r;
                vec2 c=chromaAt(uv);
                vec3 rgb=vec3(y+1.5748*c.y,y-.187324*c.x-.468124*c.y,y+1.8556*c.x);
                highp uvec2 p=uvec2(gl_FragCoord.xy);
                highp uint seed=p.x+4099u*p.y;
                float d=(float(hash32(seed)&1023u)-float(hash32(seed+0x9e3779b9u)&1023u))/1024.;
                outColor=vec4(clamp(rgb+d*uDitherStep,0.,1.),1.);
            }
        """)
'''+s[b:]
s=s.replace('(drawLocations+attributeLocation(composite)).distinct()', '(drawLocations+attributeLocation(composite)+attributeLocation(splitProgram)).distinct()')
# All inference modes use R16F for final luma.
s=s.replace('maxMode && idx == stages.lastIndex','idx == stages.lastIndex')
# Preserve duplicate-frame reuse; split once for each new input.
once("        if (!canReuse) {","        if (!canReuse) {\\n        splitFrame(video,matrix,w,h)")
s=s.replace('if(sourceIndex<0)video else targets[sourceIndex].texture','if(sourceIndex<0)sourceY else targets[sourceIndex].texture')
s=s.replace('val bindings=if(sourceIndex<0)boundExternal else bound2D','val bindings=bound2D')
s=s.replace('if(sourceIndex<0)GLES11Ext.GL_TEXTURE_EXTERNAL_OES else GLES30.GL_TEXTURE_2D','GLES30.GL_TEXTURE_2D')
# Replace all final composite bindings and old enhancement uniforms.
a=s.index('        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,outputFbo)')
b=s.index('        draw(composite)',a)
s=s[:a]+'''        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,outputFbo)
        GLES30.glViewport(0,0,outW,outH);GLES30.glUseProgram(composite)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,targets.last().texture)
        setUniform1i(composite,"uNeural",0)
        GLES30.glActiveTexture(GLES30.GL_TEXTURE1)
        GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,sourceUV)
        setUniform1i(composite,"uChroma",1)
        val neural=targets.last()
        setUniform2f(composite,"uNeuralSize",neural.w.toFloat(),neural.h.toFloat())
        setUniform2f(composite,"uChromaSize",splitW.toFloat(),splitH.toFloat())
        setUniform1f(composite,"uNeedsScale",if(outW!=neural.w || outH!=neural.h)1f else 0f)
        val bits=IntArray(1)
        GLES30.glGetIntegerv(GLES30.GL_RED_BITS,bits,0)
        setUniform1f(composite,"uDitherStep",if(bits[0]>=10)1f/1023f else 1f/255f)
'''+s[b:]
once("    fun close(){","    fun close(){\\n        releaseSplit()\\n        if(splitProgram!=0)GLES30.glDeleteProgram(splitProgram)")
# Correct matching vertex varying precision.
s=s.replace('in vec2 position;out vec2 uv;', 'in highp vec2 position;out highp vec2 uv;')
p.write_text(s)
# Standard Neural is the 8-channel model, Max is 16-channel for film.
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=s.replace('(if (maxMode) sourceFps < 50f else srcH <= 800)', '(maxMode && sourceFps > 0f && sourceFps <= 24.1f && srcH <= 800)')
# Full input resolution; no silent reduction. Runtime performance is to be tested.
s=re.sub(r'if \(slowFrames >= 2 && neuralScale > 0\.51f\) \{.*?\n\s*\}', 'if (slowFrames >= 2) { slowFrames = 0 }',s,count=1,flags=re.S)
p.write_text(s)
print("Specified zero-copy split, luma-only FP16 FSRCNNX, fused Lanczos2/chroma/TPDF compositor installed.")
