"""Isolated Reflite picture depth tuning, based on smooth 16-channel build.
Changes only scalar math in the existing final composition shader.
No extra texture samples, shader passes, network complexity, new settings,
GPU timing adjustments, audio, Plezy, or package name changes.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''                float naturalDetailBoost=clamp(
                    modelResidual*.22*tvDetailFactor*textureGate,-.021,.021);'''
b='''                // Improve already-learned neural residuals on detailed
                // 720p television textures. No extra GPU texture fetch.
                float tvTextureStrength=1.0+0.21*
                    (1.0-smoothstep(770.0,910.0,uOriginalFrameHeight));
                float naturalDetailBoost=clamp(
                    modelResidual*.22*tvDetailFactor*tvTextureStrength*
                    textureGate,-.024,.024);'''
assert s.count(a)==1, f"model residual anchor mismatch {s.count(a)}"
s=s.replace(a,b,1)
a='''                float microBoost=clamp(
                    (finalY-localMeanY)*.11*tvContrastFactor,-.015,.015);'''
b='''                // More midtone definition from the same original
                // neighbourhood already sampled for anti-halo protection.
                float tvLocalStrength=1.0+0.20*
                    (1.0-smoothstep(770.0,910.0,uOriginalFrameHeight));
                float microBoost=clamp(
                    (finalY-localMeanY)*.11*tvContrastFactor*
                    tvLocalStrength,-.017,.017);'''
assert s.count(a)==1, f"local contrast anchor mismatch {s.count(a)}"
s=s.replace(a,b,1)
a='''                float shadowDepth=.045+lowRes*.038;'''
b='''                // Slightly fuller near-black density only on 720p sources;
                // flat zero remains zero and the toe fades before midtones.
                float shadowDepth=.045+lowRes*.047;'''
assert s.count(a)==1,f"black toe anchor mismatch {s.count(a)}"
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite picture-depth-only test: stronger masked existing neural detail, masked local contrast, modest 720p black toe; no new reads.")
