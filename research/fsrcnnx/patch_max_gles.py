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
s=s.replace('srcH <= 800 &&','(if (maxMode) sourceFps < 50f else srcH <= 800) &&')
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
        composite=link(vertexShader,if(maxMode) filmSource else compositeSource)
        prepareGeometry()''')
p.write_text(s)
print("Max first-stage prototype: fps-selected model, single-channel final target and strict anti-ringing; six-frame sync preserved")
