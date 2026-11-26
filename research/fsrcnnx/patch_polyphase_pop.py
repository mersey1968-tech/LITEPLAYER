from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)
# Stronger fixed phase negative lobes; preserve DC and first moment.
once("vec3(-.082,-.057,.17442201)","vec3(-.110,-.075,.17440225)")
once("vec3(-.057,-.082,.82557799)","vec3(-.075,-.110,.82559775)")
once("vec3(-.120,-.120,.5)","vec3(-.150,-.150,.5)")
# Exact source-size gate, not a global colour adjustment.
once("                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);", """                if (uHdr < .5 && abs(uOriginalFrameHeight-720.) < .5 && abs(uSourceTexel.x*1280.-1.) < .001) {
                    float lum=dot(reconstructed,vec3(.2126,.7152,.0722));
                    vec3 chroma=reconstructed-vec3(lum);
                    float sat=max(reconstructed.r,max(reconstructed.g,reconstructed.b))-
                              min(reconstructed.r,min(reconstructed.g,reconstructed.b));
                    float warm=smoothstep(.015,.09,reconstructed.r-reconstructed.b)*
                        (1.-smoothstep(.04,.18,abs(reconstructed.g-(reconstructed.r+reconstructed.b)*.5)));
                    float guard=smoothstep(.04,.18,lum)*(1.-smoothstep(.78,.98,lum));
                    vec3 delta=chroma*(.08*guard*(1.-.70*warm)*(1.-smoothstep(.65,1.,sat)));
                    reconstructed=clamp(reconstructed+delta,0.,1.);
                    float contrastDelta=.10*lum*(1.-lum)*(2.*lum-1.);
                    float lo=min(reconstructed.r,min(reconstructed.g,reconstructed.b));
                    float hi=max(reconstructed.r,max(reconstructed.g,reconstructed.b));
                    reconstructed+=vec3(clamp(contrastDelta,-lo,1.-hi));
                }
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);""")
p.write_text(s)
# 720p native-resolution policy already forbids adaptive downscaling.
# Skip periodic blocking completion samples only at exact 720p:
# the quality floor means those samples cannot lower resolution.
p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
once("val sampleGpu = newFrame && (++presentedFrames % 8 == 0)",
     "val sampleGpu = newFrame && !(srcW == 1280 && srcH == 720 && neuralScale >= 1.0f) && (++presentedFrames % 8 == 0)")
p.write_text(s)
print("720p pop and nonblocking native-resolution timing; no added presentation delay")
