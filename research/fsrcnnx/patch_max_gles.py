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
s=s.replace('FsrcnnxPipeline(trainedModel)','FsrcnnxPipeline(trainedModel, maxMode, maxMode && srcW <= 1280 && srcH <= 800)').replace('FsrcnnxPipeline(model16)','FsrcnnxPipeline(model16, maxMode, maxMode && srcW <= 1280 && srcH <= 800)').replace('FsrcnnxPipeline(neuralModel16)','FsrcnnxPipeline(neuralModel16, maxMode, maxMode && srcW <= 1280 && srcH <= 800)')
s=s.replace('srcH <= 800 &&','(if (maxMode) sourceFps < 50f && srcH <= 800 && srcW <= 1280 else srcH <= 800) &&')
p.write_text(s)
p=root/"FsrcnnxPipeline.kt"
s=p.read_text()
s=once(s,'internal class FsrcnnxPipeline(raw: String)','internal class FsrcnnxPipeline(raw: String, private val maxMode:Boolean=false, private val maxSpline:Boolean=false)')
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
        // Spline36 is used only when a <=720p source needs the final enlargement.
        // Combine the central positive pair via hardware bilinear interpolation.
        // The other four taps have alternating signs and must remain separate.
        val splineCode = """
            float spline36Weight(float x) {
                x=abs(x);
                if(x<1.0) return ((13.0/11.0*x-453.0/209.0)*x-3.0/209.0)*x+1.0;
                if(x<2.0) {x-=1.0;return ((-6.0/11.0*x+270.0/209.0)*x-156.0/209.0)*x;}
                if(x<3.0) {x-=2.0;return ((1.0/11.0*x-45.0/209.0)*x+26.0/209.0)*x;}
                return 0.0;
            }
            float cubicNeural(vec2 pos) {
                vec2 x=pos*uNeuralSize-0.5;
                vec2 b=floor(x), f=fract(x);
                vec2 c0=vec2(spline36Weight(f.x),spline36Weight(f.y));
                vec2 c1=vec2(spline36Weight(1.0-f.x),spline36Weight(1.0-f.y));
                vec2 center=c0+c1;
                vec2 wt[5];
                wt[0]=vec2(spline36Weight(2.0+f.x),spline36Weight(2.0+f.y));
                wt[1]=vec2(spline36Weight(1.0+f.x),spline36Weight(1.0+f.y));
                wt[2]=center;
                wt[3]=vec2(spline36Weight(2.0-f.x),spline36Weight(2.0-f.y));
                wt[4]=vec2(spline36Weight(3.0-f.x),spline36Weight(3.0-f.y));
                vec2 p[5];
                p[0]=(b-1.5)/uNeuralSize;
                p[1]=(b-0.5)/uNeuralSize;
                p[2]=(b+0.5+c1/center)/uNeuralSize;
                p[3]=(b+2.5)/uNeuralSize;
                p[4]=(b+3.5)/uNeuralSize;
                float sum=0.0, norm=0.0;
                for(int j=0;j<5;j++) for(int i=0;i<5;i++) {
                    float w=wt[i].x*wt[j].y;
                    sum+=w*texture(uNeural,vec2(p[i].x,p[j].y)).r;
                    norm+=w;
                }
                ivec2 k=ivec2(b), lim=ivec2(uNeuralSize)-1;
                float n0=texelFetch(uNeural,clamp(k,ivec2(0),lim),0).r;
                float n1=texelFetch(uNeural,clamp(k+ivec2(1,0),ivec2(0),lim),0).r;
                float n2=texelFetch(uNeural,clamp(k+ivec2(0,1),ivec2(0),lim),0).r;
                float n3=texelFetch(uNeural,clamp(k+ivec2(1,1),ivec2(0),lim),0).r;
                float lo=min(min(n0,n1),min(n2,n3));
                float hi=max(max(n0,n1),max(n2,n3));
                float margin=min(0.012,0.12*(hi-lo));
                return clamp(sum/norm,lo-margin,hi+margin);
            }
        """.trimIndent()
        val splineSource = if (maxSpline) {
            val start=maxSource.indexOf("float cubicNeural(vec2 pos) {")
            val end=maxSource.indexOf("void main(){",start)
            check(start>=0 && end>start)
            maxSource.substring(0,start)+splineCode+"\\n"+maxSource.substring(end)
        } else maxSource
        composite=link(vertexShader,if(maxMode) splineSource else compositeSource)
        prepareGeometry()''')
p.write_text(s)
print("Max first-stage prototype: fps-selected model, single-channel final target and strict anti-ringing; six-frame sync preserved")
