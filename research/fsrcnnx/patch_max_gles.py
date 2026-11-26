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
p.write_text(s)
p=root/"FsrcnnxPipeline.kt"
s=p.read_text()
s=once(s,'internal class FsrcnnxPipeline(raw: String)','internal class FsrcnnxPipeline(raw: String, private val maxMode:Boolean=false)')
s=once(s,'private fun allocate(w:Int,h:Int):Target','private fun allocate(w:Int,h:Int,single:Boolean=false):Target')
s=once(s,'GLES30.GL_RGBA16F,w,h,0,GLES30.GL_RGBA,GLES30.GL_HALF_FLOAT','if(single) GLES30.GL_R16F else GLES30.GL_RGBA16F,w,h,0,if(single) GLES30.GL_RED else GLES30.GL_RGBA,GLES30.GL_HALF_FLOAT')
s=once(s,'else allocate(tw,th)','else allocate(tw,th,maxMode && idx == stages.lastIndex)')
# Final composition: remove cubic reconstruction entirely. Hardware linear
# sampling of the trained 2x luma output is the low-cost baseline.
import re
s,n=re.subn(r'float cubicNeural\(vec2 pos\)\s*\{.*?\n\s*\}', '', s,count=1,flags=re.S)
assert n==1
s=once(s,'uCubicNeural>0.5?cubicNeural(uv):texture(uNeural,uv).r','texture(uNeural,uv).r')
# Keep standard mode's existing detail math. Max alone gets texture recovery.
s=once(s,'        composite=link(vertexShader,"""','        val compositeSource="""')
s=once(s,'        """)\n        prepareGeometry()','''        """
        val textureSource=compositeSource
            .replace("float modelResidual=clamp(protectedY-orig,-.095,.095);",
                "float rawY=dot(rawRgb,vec3(.2126,.7152,.0722)); float modelResidual=clamp(y-rawY,-.095,.095);")
            .replace("smoothstep(.015,.055,contrast)", "smoothstep(.007,.030,contrast)")
            .replace("finalY=clamp(finalY+microBoost*textureMask*edgeMask*toneMask,",
                "finalY=clamp(finalY+microBoost*textureMask*edgeMask*toneMask,")
            .replace("minY-.025,maxY+.025);",
                "minY-mix(.025,.055,(1.0-edge)*textureGate),maxY+mix(.025,.055,(1.0-edge)*textureGate));")
        check(textureSource.contains("float rawY=") && textureSource.contains("smoothstep(.007,.030,contrast)") && textureSource.contains("minY-mix(.025,.055"))
        composite=link(vertexShader,if(maxMode) textureSource else compositeSource)
        prepareGeometry()''')
assert 'cubicNeural(' not in s
p.write_text(s)
print("Texture recovery: raw-source learned residual, softer texture threshold, adaptive output headroom, linear final resampling; no new fetches.")
