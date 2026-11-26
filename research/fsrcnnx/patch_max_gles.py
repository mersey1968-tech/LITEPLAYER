from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
p=root/"MainActivity.kt"
s=p.read_text()
s=once(s,"    private var referenceScalerEnabled = false","    private var referenceScalerEnabled = false\n    private var referenceMax = false")
s=once(s,'"FSRCNNX Neural (SDR)"','"FSRCNNX Neural (SDR)", "Max"')
s=once(s,'if (referenceScalerEnabled) 1 else 0','if (!referenceScalerEnabled) 0 else if (referenceMax) 2 else 1')
s=once(s,'                referenceScalerEnabled = which == 1','''                val nextMax = which == 2
                if (referenceMax != nextMax && scalerView != null) {
                    referenceScalerEnabled = false
                    applyRefliteScaler()
                }
                referenceMax = nextMax
                referenceScalerEnabled = which != 0''')
s=once(s,'.putBoolean("neural_enabled", referenceScalerEnabled).apply()','.putBoolean("neural_enabled", referenceScalerEnabled).putBoolean("max_enabled", referenceMax).apply()')
s=s.replace('            .getBoolean("neural_enabled", false)','            .getBoolean("neural_enabled", false)\n        referenceMax = getSharedPreferences("reflite_video", MODE_PRIVATE).getBoolean("max_enabled", false)')
s=once(s,'ReferenceScalerView(this)','ReferenceScalerView(this, referenceMax, fmt.frameRate.takeIf { it > 0f } ?: videoFps)')
assert 'val distance = (6000.0 / fps).toLong().coerceAtLeast(1L)' in s
assert 'activePlayer.seekTo(position - distance)' in s
p.write_text(s)
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=once(s,'context: Context','context: Context, private val maxMode: Boolean = false, private val sourceFps: Float = 24f')
s=s.replace('FsrcnnxPipeline(trainedModel)','FsrcnnxPipeline(trainedModel, maxMode)').replace('FsrcnnxPipeline(model16)','FsrcnnxPipeline(model16, maxMode)').replace('FsrcnnxPipeline(neuralModel16)','FsrcnnxPipeline(neuralModel16, maxMode)')
s=s.replace('srcH <= 800 &&','(if (maxMode) sourceFps < 50f && srcH <= 800 && srcW <= 1280 else srcH <= 800) &&')
# Max low-resolution film path must not silently run neural inference at reduced size.
s=once(s,'if (slowFrames >= 2 && neuralScale > 0.51f)', 'if (!(maxMode && srcW <= 1280 && srcH <= 800 && sourceFps < 50f) && slowFrames >= 2 && neuralScale > 0.51f)')
p.write_text(s)
p=root/"FsrcnnxPipeline.kt"
s=p.read_text()
s=once(s,'internal class FsrcnnxPipeline(raw: String)','internal class FsrcnnxPipeline(raw: String, private val maxMode:Boolean=false)')
s=once(s,'private fun allocate(w:Int,h:Int):Target','private fun allocate(w:Int,h:Int,single:Boolean=false):Target')
s=once(s,'GLES30.GL_RGBA16F,w,h,0,GLES30.GL_RGBA,GLES30.GL_HALF_FLOAT','if(single) GLES30.GL_R16F else GLES30.GL_RGBA16F,w,h,0,if(single) GLES30.GL_RED else GLES30.GL_RGBA,GLES30.GL_HALF_FLOAT')
s=once(s,'else allocate(tw,th)','else allocate(tw,th,maxMode && idx == stages.lastIndex)')
# Use strict nearest-neighbour extrema for final secondary scaling, only in Max.
s=once(s,'return clamp(cubic,lo-0.025,hi+0.025);','''return clamp(cubic,lo-0.025,hi+0.025);''')
# Inject mode-specific composite GLSL before shader compilation, retaining original shader in standard mode.
s=once(s,'        composite=link(vertexShader,"""','        val compositeSource="""')
s=once(s,'        """)\n        prepareGeometry()','''        """
        val maxSource = compositeSource.replace("return clamp(cubic,lo-0.025,hi+0.025);", """
            ivec2 b0=ivec2(base);
            ivec2 lim=ivec2(uNeuralSize)-ivec2(1);
            float n0=texelFetch(uNeural,clamp(b0,ivec2(0),lim),0).r;
            float n1=texelFetch(uNeural,clamp(b0+ivec2(1,0),ivec2(0),lim),0).r;
            float n2=texelFetch(uNeural,clamp(b0+ivec2(0,1),ivec2(0),lim),0).r;
            float n3=texelFetch(uNeural,clamp(b0+ivec2(1,1),ivec2(0),lim),0).r;
            return clamp(cubic,min(min(n0,n1),min(n2,n3)),max(max(n0,n1),max(n2,n3)));
        """.trimIndent())
        // Film detail: retain original trained reconstruction and avoid
        // averaging away low-contrast source texture on low-resolution material.
        val filmSource=maxSource.replace(
            "rgb=mix(rawRgb,weighted/total,mix(0.22,0.08,1.0-smoothstep(770.0,910.0,uOriginalFrameHeight))*detailProtection);",
            "rgb=mix(rawRgb,weighted/total,0.22*smoothstep(770.0,910.0,uOriginalFrameHeight)*detailProtection);")
            .replace("return clamp(cubic,min(min(n0,n1),min(n2,n3)),max(max(n0,n1),max(n2,n3)));",
                "float lo4=min(min(n0,n1),min(n2,n3)); float hi4=max(max(n0,n1),max(n2,n3)); float margin=min(0.008,0.10*(hi4-lo4))*(1.0-smoothstep(770.0,910.0,uOriginalFrameHeight)); return clamp(cubic,lo4-margin,hi4+margin);")
        check(filmSource.contains("float lo4=") && filmSource.contains("0.22*smoothstep(770.0,910.0,uOriginalFrameHeight)"))
        // Exact separable Catmull-Rom: only combine the positive central
        // pair. Negative outer lobes must retain their own sample locations.
        val cubicFix = """
            float cubicNeural(vec2 pos) {
                vec2 x=pos*uNeuralSize-vec2(0.5);
                vec2 f=fract(x), b=floor(x);
                vec2 f2=f*f, f3=f2*f;
                vec2 w0=-0.5*f+f2-0.5*f3;
                vec2 w1=1.0-2.5*f2+1.5*f3;
                vec2 w2=0.5*f+2.0*f2-1.5*f3;
                vec2 w3=-0.5*f2+0.5*f3;
                vec2 mid=w1+w2;
                vec2 p0=(b-vec2(0.5))/uNeuralSize;
                vec2 p1=(b+vec2(0.5)+w2/mid)/uNeuralSize;
                vec2 p2=(b+vec2(2.5))/uNeuralSize;
                float v00=texture(uNeural,vec2(p0.x,p0.y)).r;
                float v10=texture(uNeural,vec2(p1.x,p0.y)).r;
                float v20=texture(uNeural,vec2(p2.x,p0.y)).r;
                float v01=texture(uNeural,vec2(p0.x,p1.y)).r;
                float v11=texture(uNeural,vec2(p1.x,p1.y)).r;
                float v21=texture(uNeural,vec2(p2.x,p1.y)).r;
                float v02=texture(uNeural,vec2(p0.x,p2.y)).r;
                float v12=texture(uNeural,vec2(p1.x,p2.y)).r;
                float v22=texture(uNeural,vec2(p2.x,p2.y)).r;
                float y0=w0.x*v00+mid.x*v10+w3.x*v20;
                float y1=w0.x*v01+mid.x*v11+w3.x*v21;
                float y2=w0.x*v02+mid.x*v12+w3.x*v22;
                float cubic=w0.y*y0+mid.y*y1+w3.y*y2;
                ivec2 q=ivec2(b), lim=ivec2(uNeuralSize)-ivec2(1);
                float n0=texelFetch(uNeural,clamp(q,ivec2(0),lim),0).r;
                float n1=texelFetch(uNeural,clamp(q+ivec2(1,0),ivec2(0),lim),0).r;
                float n2=texelFetch(uNeural,clamp(q+ivec2(0,1),ivec2(0),lim),0).r;
                float n3=texelFetch(uNeural,clamp(q+ivec2(1,1),ivec2(0),lim),0).r;
                float lo=min(min(n0,n1),min(n2,n3)), hi=max(max(n0,n1),max(n2,n3));
                float margin=min(0.008,0.10*(hi-lo));
                return clamp(cubic,lo-margin,hi+margin);
            }
        """.trimIndent()
        val start=filmSource.indexOf("float cubicNeural(vec2 pos) {")
        val end=filmSource.indexOf("void main(){",start)
        check(start>=0 && end>start)
        val correctedSource=filmSource.substring(0,start)+cubicFix+"\\n"+filmSource.substring(end)
        composite=link(vertexShader,if(maxMode) correctedSource else compositeSource)
        prepareGeometry()''')
p.write_text(s)
print("Max first-stage prototype: fps-selected model, single-channel final target and strict anti-ringing; six-frame sync preserved")
