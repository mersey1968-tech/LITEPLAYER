"""Reflite-only deep black enhancement after resolution-aware neural detail.
Gentle toe curve darkens near-blacks without clipping or touching midtones/highlights.
No extra UI settings; never alters known-good Reflite/LitePlayer.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''                vec3 reconstructed=clamp(rgb+vec3(finalY-orig),0.,1.);
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);'''
b='''                // Gently deepen near-black SDR tones without subtracting a
                // fixed offset (which crushes shadow detail). Input black maps
                // exactly to output black. Midtones and highlights are intact.
                float shadowToe=1.0-smoothstep(.025,.24,finalY);
                float deeperY=finalY*(1.0-.085*shadowToe);
                vec3 reconstructed=clamp(rgb+vec3(deeperY-orig),0.,1.);
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);'''
if s.count(a)!=1:raise RuntimeError(f"output compose match {s.count(a)}")
s=s.replace(a,b,1)
p.write_text(s)
print("Subtle 8.5% maximum near-black toe (preserves black point, shadow texture and midtones) staged")
