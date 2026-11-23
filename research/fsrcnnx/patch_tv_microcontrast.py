"""Subtle local midtone microcontrast, integrated into Reflite TV neural output.
Runs AFTER natural-detail, automatic TV cleanup and 720p-to-4K patches.
No new user control, no changes to preserved known-good Reflite/LitePlayer.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''                float minY=orig;
                float maxY=orig;
                for(int i=0;i<4;i++) {'''
b='''                float minY=orig;
                float maxY=orig;
                float localMeanY=orig;
                for(int i=0;i<4;i++) {'''
if s.count(a)!=1:raise RuntimeError(f"microcontrast mean marker ambiguous: {s.count(a)}")
s=s.replace(a,b,1)
a='''                    minY=min(minY,l);maxY=max(maxY,l);
                }
                float contrast=maxY-minY;'''
b='''                    minY=min(minY,l);maxY=max(maxY,l);
                    localMeanY+=l;
                }
                localMeanY*=0.2;
                float contrast=maxY-minY;'''
if s.count(a)!=1:raise RuntimeError(f"microcontrast average marker ambiguous: {s.count(a)}")
s=s.replace(a,b,1)
a='''                float finalY=mix(y,protectedY,edge);
                vec3 reconstructed=clamp(rgb+vec3(finalY-orig),0.,1.);'''
b='''                float finalY=mix(y,protectedY,edge);
                // Subtle adaptive microcontrast for TV episodes: use 5 samples
                // already gathered for anti-halo protection, no extra texture
                // fetches. Lift true textured midtones but not flat compression
                // noise, shadow blacks, clipped highlights or hard edge halos.
                float textureMask=smoothstep(.025,.075,contrast);
                float edgeMask=1.0-smoothstep(.19,.37,contrast);
                float toneMask=smoothstep(.06,.20,orig) *
                               (1.0-smoothstep(.82,.96,orig));
                float microBoost=clamp((finalY-localMeanY)*.11,-.012,.012);
                finalY=clamp(finalY+microBoost*textureMask*edgeMask*toneMask,
                             minY-.025,maxY+.025);
                vec3 reconstructed=clamp(rgb+vec3(finalY-orig),0.,1.);'''
if s.count(a)!=1:raise RuntimeError(f"microcontrast output marker ambiguous: {s.count(a)}")
s=s.replace(a,b,1)
p.write_text(s)
print("Subtle texture-gated midtone microcontrast integrated with zero additional taps.")
