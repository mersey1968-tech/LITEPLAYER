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
# Replace the old reconstruction function in both modes, not just Max.
import re
shader = """float jincApprox(float t) {
    // J1(pi*r)*2/(pi*r), evaluated in squared radius via Horner.
    float z=t*2.46740110027234;
    return 1.0+z*(-0.5+z*(0.0833333333333+z*(-0.00694444444444+z*(0.000347222222222+z*(-0.0000115740740741+z*(0.00000027557319224+z*(-0.00000000492094986+z*(0.000000000068346526+z*(-0.00000000000075940584+z*0.00000000000000690369)))))))));
}
float ewaNeural(vec2 pos) {
    highp vec2 pixel=pos*uNeuralSize-0.5;
    ivec2 base=ivec2(floor(pixel));
    highp vec2 f=fract(pixel);
    ivec2 lim=ivec2(uNeuralSize)-ivec2(1);
    highp float acc=0.0, total=0.0;
    highp float lo=1.0, hi=0.0;
    for(int j=-3;j<=4;j++) {
        for(int i=-3;i<=4;i++) {
            highp vec2 d=vec2(float(i),float(j))-f;
            highp float r2=dot(d,d)/0.962852708;
            if(r2<10.486687) {
                highp float w=jincApprox(r2)*jincApprox(r2*0.141858);
                float v=texelFetch(uNeural,clamp(base+ivec2(i,j),ivec2(0),lim),0).r;
                acc+=w*v; total+=w;
                if(i>=0 && i<=1 && j>=0 && j<=1) {
                    lo=min(lo,v); hi=max(hi,v);
                }
            }
        }
    }
    float y=acc/max(total,0.0001);
    return mix(y,clamp(y,lo,hi),0.5);
}
"""
s,n=re.subn(r'float cubicNeural\(vec2 pos\)\s*\{.*?\n\s*\}',lambda m:shader,s,count=1,flags=re.S)
assert n==1
s=s.replace("cubicNeural(uv)","ewaNeural(uv)").replace("uCubicNeural","uEwaNeural")
assert "cubicNeural" not in s
# Apply EWA whenever neural output and display size differ, including fallback sizes.
s=s.replace("val cubic720=h <= 800 && outH > neural.h && outH >= 1600","val cubic720=outH != neural.h || outW != neural.w")
p.write_text(s)
print("Jinc reconstruction installed; no cubic function remains in neural compositor.")
