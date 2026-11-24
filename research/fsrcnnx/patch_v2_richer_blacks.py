"""Reflite v2: richer black floor and selective local midtone separation.
Apply only after patch_v2_warmup_detail.py. No new switches, no alteration
of full-scale peak, no crushing of exact-black pixels or detail.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''                vec3 reconstructed=clamp(rgb+vec3(finalY-orig),0.,1.);
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);'''
b='''                vec3 reconstructed=clamp(rgb+vec3(finalY-orig),0.,1.);
                // Mild nonlinear SDR shadow toe: preserves black at 0, leaves
                // mids and highlights alone. More pronounced for soft SD/720p
                // television than high-quality 1080p masters.
                float lowRes=1.0-smoothstep(770.,910.,uOriginalFrameHeight);
                float shadowRange=1.0-smoothstep(.020,.275,finalY);
                float shadowDepth=.045+lowRes*.038;
                reconstructed*=1.0-shadowDepth*shadowRange;
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);'''
assert s.count(a)==1,f"final SDR output match: {s.count(a)}"
s=s.replace(a,b,1)
p.write_text(s)
print("Mild deeper blacks for soft TV sources without shadows being clipped.")
