"""Reflite v2 stability/perceptual detail test on an isolated branch.

Precompile the proven 16-channel model before the video decoder surface is
provided, eliminating the expensive 26-stage shader compilation that previously
occurred on the first actual playing frame.

Enhance 540p/720p trained-neural detail using existing shader samples only:
no new texture reads, no changes to codec, audio, AFR or Plezy identity.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
a='''            neuralPipeline = FsrcnnxPipeline(trainedModel)
            if (hdrRequested && !hdrSurfaceActive) {'''
b='''            neuralPipeline = FsrcnnxPipeline(trainedModel)
            // Precompile the stronger model BEFORE opening the decoder surface.
            // The previous version compiled 26 shaders synchronously while the
            // first decoded video frame was waiting to be rendered.
            if (neural16Pipeline == null && !neural16Unavailable) {
                try {
                    val model16 = context.assets.open(
                        "reflite/FSRCNNX_x2_16-0-4-1.glsl")
                        .bufferedReader().use { it.readText() }
                    neural16Pipeline = FsrcnnxPipeline(model16)
                    Log.i("Reflite V2", "16-channel neural pipeline primed before playback")
                } catch (error: Throwable) {
                    neural16Unavailable = true
                    Log.e("Reflite V2", "16-channel priming unavailable: " +
                        error.message + "; normal 8-channel fallback retained")
                }
            }
            if (hdrRequested && !hdrSurfaceActive) {'''
assert s.count(a)==1, "onSurfaceCreated model creation location changed"
s=s.replace(a,b,1)
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''            uniform vec2 uNeuralSize;
            uniform float uCubicNeural;'''
b='''            uniform vec2 uNeuralSize;
            uniform float uOriginalFrameHeight;
            uniform float uCubicNeural;'''
assert s.count(a)==1, "shader uniform location changed"
s=s.replace(a,b,1)
a='''                float naturalDetailBoost=clamp(modelResidual*.22*textureGate,-.016,.016);'''
b='''                // Stronger learned reconstruction specifically for soft TV
                // material. Preserve the successful 1080p behavior untouched.
                float tvDetailFactor=1.0+0.55*
                    (1.0-smoothstep(770.0,910.0,uOriginalFrameHeight));
                float naturalDetailBoost=clamp(
                    modelResidual*.22*tvDetailFactor*textureGate,-.021,.021);'''
assert s.count(a)==1, "original learned residual missing"
s=s.replace(a,b,1)
a='''                float microBoost=clamp((finalY-localMeanY)*.11,-.012,.012);'''
b='''                // Modest source-dependent microcontrast. The existing
                // texture/edge masks prevent flat wall noise and black halos.
                float tvContrastFactor=1.0+0.30*
                    (1.0-smoothstep(770.0,910.0,uOriginalFrameHeight));
                float microBoost=clamp(
                    (finalY-localMeanY)*.11*tvContrastFactor,-.015,.015);'''
assert s.count(a)==1, "existing texture-gated local contrast missing"
s=s.replace(a,b,1)
a='''        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uNeuralSize"),neural.w.toFloat(),neural.h.toFloat())'''
b='''        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uNeuralSize"),neural.w.toFloat(),neural.h.toFloat())
        GLES30.glUniform1f(GLES30.glGetUniformLocation(composite,"uOriginalFrameHeight"),
            originalFrameHeight.toFloat())'''
assert s.count(a)==1,"neural uniforms missing"
s=s.replace(a,b,1)
a='''diagnostic:Boolean,hdr:Boolean=false,outputFbo:Int=0) {'''
b='''diagnostic:Boolean,hdr:Boolean=false,outputFbo:Int=0,
               originalFrameHeight:Int=h) {'''
assert s.count(a)==1,"render function signature changed"
s=s.replace(a,b,1)
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
a='''            selected?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false)'''
b='''            selected?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false, originalFrameHeight=srcH)'''
assert s.count(a)==1,"16-channel selected render missing"
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite v2 primed 16-channel model and stronger bounded 540p/720p learned detail and local contrast.")
