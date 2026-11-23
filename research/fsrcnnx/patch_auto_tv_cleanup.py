"""Automatic TV-episode spatial cleanup: no new switches, no changes to playback UX.
Runs after isolated natural-detail patch. Edge- and texture-aware gentle bilateral cleanup.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''                float y=texture(uNeural,uv).r;
                vec3 rgb=texture(uVideo,(uMatrix*vec4(uv,0.,1.)).xy).rgb;
                float orig=dot(rgb,vec3(0.2126,0.7152,0.0722));'''
b='''                float y=texture(uNeural,uv).r;
                vec3 rawRgb=texture(uVideo,(uMatrix*vec4(uv,0.,1.)).xy).rgb;
                vec3 rgb=rawRgb;
                // Automatic, conservative spatial denoising for compressed
                // television: only average nearby pixels with similar colour.
                // Protect texture, line detail and high-contrast boundaries.
                vec3 weighted=rawRgb;
                float total=1.;
                float variation=0.;
                for(int i=0;i<4;i++) {
                    vec2 shift=(i==0?vec2(uSourceTexel.x,0.) :
                                i==1?vec2(-uSourceTexel.x,0.) :
                                i==2?vec2(0.,uSourceTexel.y) :
                                     vec2(0.,-uSourceTexel.y));
                    vec3 n=texture(uVideo,(uMatrix*vec4(uv+shift,0.,1.)).xy).rgb;
                    float delta=dot(abs(n-rawRgb),vec3(.25,.5,.25));
                    float rangeWeight=exp(-delta*delta*900.);
                    weighted+=rangeWeight*n;
                    total+=rangeWeight;
                    variation+=delta;
                }
                float detailProtection=1.0-smoothstep(.028,.095,variation*.25);
                rgb=mix(rawRgb,weighted/total,0.22*detailProtection);
                float orig=dot(rgb,vec3(0.2126,0.7152,0.0722));'''
if s.count(a)!=1:raise RuntimeError(f"match expected 1 got {s.count(a)}")
s=s.replace(a,b,1)
p.write_text(s)
print("Automatic Gentle TV cleanup integrated into FSRCNNX. No new switches or user controls.")
