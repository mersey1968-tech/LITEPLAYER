"""Resolution-aware neural detail reconstruction for Reflite TV episodes.

Build staging only. Leaves stable LitePlayer & known-good Reflite intact.
Includes no new user controls, diagnostics are Android logcat only.
Applies after patch_playback_and_real_detail.py, so its original safer
GPU fallback and synchronous Plezy exit are preserved.
"""
from pathlib import Path

p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
def once(old,new):
    global s
    n=s.count(old)
    if n!=1:raise RuntimeError(f"shader expected one match, got {n}: {old[:100]!r}")
    s=s.replace(old,new,1)

once('''            uniform vec2 uNeuralSize;
            uniform float uCubicNeural;''','''            uniform vec2 uNeuralSize;
            uniform float uOriginalSourceHeight;
            uniform float uCubicNeural;''')
once('''                float y=uCubicNeural>0.5?cubicNeural(uv):texture(uNeural,uv).r;''','''                float y=uCubicNeural>0.5?cubicNeural(uv):texture(uNeural,uv).r;
                // True x2 model subpixel output, measured at final output.
                // Source-dependent restoration: 540p and 720p benefit more
                // than 1080p. Only sample additional neural pixels below 900p.
                float lowRes=uOriginalSourceHeight<650.0?1.0:0.0;
                float hd720=(uOriginalSourceHeight>=650.0 &&
                             uOriginalSourceHeight<900.0)?1.0:0.0;
                float detailClass=max(lowRes,hd720);
                float neuralHighpass=0.0;
                if(detailClass>0.5) {
                    vec2 d=1.0/uNeuralSize;
                    float n0=texture(uNeural,uv+vec2(d.x,0.0)).r;
                    float n1=texture(uNeural,uv-vec2(d.x,0.0)).r;
                    float n2=texture(uNeural,uv+vec2(0.0,d.y)).r;
                    float n3=texture(uNeural,uv-vec2(0.0,d.y)).r;
                    neuralHighpass=y-(n0+n1+n2+n3)*0.25;
                }''')
once('''                float naturalDetailBoost=clamp(modelResidual*.22*textureGate,-.016,.016);
                float finalY=mix(y,protectedY,edge)+naturalDetailBoost;''','''                // Model residual comes from learned subpixel convolution.
                // Do not replace it with generic edge sharpening.
                float residualGain=mix(.22,.48,hd720)+lowRes*.12;
                float naturalDetailBoost=clamp(modelResidual*residualGain*textureGate,
                                                -.027,.027);
                float highpassGain=lowRes*.37+hd720*.28;
                float highpassTextureGate=smoothstep(.012,.07,contrast)*
                                         (1.0-smoothstep(.23,.48,contrast));
                float highpassDetail=clamp(neuralHighpass*highpassGain*
                                            highpassTextureGate,-.021,.021);
                float finalY=mix(y,protectedY,edge)+naturalDetailBoost+highpassDetail;''')
once('''                float microBoost=clamp((finalY-localMeanY)*.11,-.012,.012);''','''                float contrastGain=.11+hd720*.075+lowRes*.09;
                float microBoost=clamp((finalY-localMeanY)*contrastGain,-.018,.018);''')
once('''        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uNeuralSize"),neural.w.toFloat(),neural.h.toFloat())''','''        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uNeuralSize"),neural.w.toFloat(),neural.h.toFloat())
        GLES30.glUniform1f(GLES30.glGetUniformLocation(composite,"uOriginalSourceHeight"),sourceHeight.toFloat())''')
once('''diagnostic:Boolean,hdr:Boolean=false,outputFbo:Int=0) {''','''diagnostic:Boolean,hdr:Boolean=false,outputFbo:Int=0,sourceHeight:Int=h) {''')
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
a='''            neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false)'''
b='''            neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false, sourceHeight=srcH)
            if (newFrame && presentedFrames % 240 == 0) {
                Log.i("Reflite Neural",
                    "Source="+srcW+"x"+srcH+" neuralWork="+workW+"x"+workH+
                    " output="+outW+"x"+outH+" detailMode="+
                    (if(srcH<650) "540p strong" else if(srcH<900) "720p strong" else "1080p natural"))
            }'''
n=s.count(a)
if n!=1:raise RuntimeError(f"renderer call expected 1 got {n}")
s=s.replace(a,b,1)
p.write_text(s)
print("Strong resolution-aware neural reconstruction staged; no UI changes; fallback and playback exit retained")
