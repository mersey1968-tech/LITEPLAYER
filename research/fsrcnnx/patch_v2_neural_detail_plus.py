"""Detail-plus: recover more apparent structure from the trained 16-channel output.

Applies only to 540p/720p (1080p unchanged). The new neural-space
high-pass operates on FSRCNNX's learned 2x output rather than simply
sharpening the decoder pixels, and uses the already calculated original
source neighbourhood to prevent hard-edge halos and amplified block noise.

Previous v2 model and black-level curve remain intact. The old build
remains accessible on reflite-v2-warmup-detail-test.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
needle='''                float finalY=mix(y,protectedY,edge)+naturalDetailBoost;'''
assert s.count(needle)==1, f"expected exactly one neural detail anchor, saw {s.count(needle)}"
replace='''                float finalY=mix(y,protectedY,edge)+naturalDetailBoost;

                // Texture-only unsharp residual from actual learned neural
                // luma; never apply globally to the compressed source. The
                // 2x model recovers structure that plain decoder sharpening
                // cannot provide. Mask flat surfaces, skin shadows, bright
                // clipping and ringing-prone large edges.
                vec2 neuralStep=1.0/uNeuralSize;
                float neuralLeft=texture(uNeural,uv-vec2(neuralStep.x,0.)).r;
                float neuralRight=texture(uNeural,uv+vec2(neuralStep.x,0.)).r;
                float neuralUp=texture(uNeural,uv+vec2(0.,neuralStep.y)).r;
                float neuralDown=texture(uNeural,uv-vec2(0.,neuralStep.y)).r;
                float neuralHighPass=y-.25*
                    (neuralLeft+neuralRight+neuralUp+neuralDown);
                float lowResMask=1.0-smoothstep(770.,900.,uOriginalFrameHeight);
                float texturedMask=smoothstep(.024,.075,contrast)*
                    (1.0-smoothstep(.18,.33,contrast));
                float visibleTones=smoothstep(.07,.19,orig)*
                    (1.0-smoothstep(.87,.98,orig));
                float neuralFineDetail=clamp(neuralHighPass*.62,-.022,.022)*
                    lowResMask*texturedMask*visibleTones;
                finalY=clamp(finalY+neuralFineDetail,
                    minY-.035,maxY+.035);'''
s=s.replace(needle,replace,1)
p.write_text(s)
print("Added bounded 4-neighbor neural-texture detail reconstruction for <=720p only")
