"""Natural-detail, edge-constrained neural reconstruction.
Runs on the isolated Reflite build ONLY, after the FSRCNNX source is copied.
Preserves original LitePlayer, the known-good Reflite branch, and subtitle code.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''            uniform mat4 uMatrix;uniform float uDiagnostic;
            uniform float uHdr;'''
b='''            uniform mat4 uMatrix;uniform float uDiagnostic;
            uniform vec2 uSourceTexel;
            uniform float uHdr;'''
assert s.count(a)==1,(a,s.count(a))
s=s.replace(a,b,1)
a='''                float y=texture(uNeural,uv).r;
                vec3 rgb=texture(uVideo,(uMatrix*vec4(uv,0.,1.)).xy).rgb;
                float orig=dot(rgb,vec3(0.2126,0.7152,0.0722));
                vec3 reconstructed=clamp(rgb+vec3(y-orig),0.,1.);'''
b='''                float y=texture(uNeural,uv).r;
                vec3 rgb=texture(uVideo,(uMatrix*vec4(uv,0.,1.)).xy).rgb;
                float orig=dot(rgb,vec3(0.2126,0.7152,0.0722));
                // Constrain learned detail to the source neighbourhood near
                // contrast edges: prevent dark/bright ringing without
                // applying indiscriminate sharpening or destroying film grain.
                vec2 sx=vec2(uSourceTexel.x,0.);
                vec2 sy=vec2(0.,uSourceTexel.y);
                float minY=orig;
                float maxY=orig;
                for(int i=0;i<4;i++) {
                    vec2 shift = i==0 ? sx : i==1 ? -sx : i==2 ? sy : -sy;
                    vec3 n=texture(uVideo,(uMatrix*vec4(uv+shift,0.,1.)).xy).rgb;
                    float l=dot(n,vec3(0.2126,0.7152,0.0722));
                    minY=min(minY,l);maxY=max(maxY,l);
                }
                float contrast=maxY-minY;
                float edge=smoothstep(0.12,0.32,contrast);
                float margin=mix(0.075,0.018,edge);
                float protectedY=clamp(y,minY-margin,maxY+margin);
                float finalY=mix(y,protectedY,edge);
                vec3 reconstructed=clamp(rgb+vec3(finalY-orig),0.,1.);'''
assert s.count(a)==1,(a,s.count(a))
s=s.replace(a,b,1)
a='''        GLES30.glUniformMatrix4fv(GLES30.glGetUniformLocation(composite,"uMatrix"),1,false,matrix,0)
        GLES30.glUniform1f(GLES30.glGetUniformLocation(composite,"uDiagnostic"),if(diagnostic)1f else 0f)'''
b='''        GLES30.glUniformMatrix4fv(GLES30.glGetUniformLocation(composite,"uMatrix"),1,false,matrix,0)
        GLES30.glUniform2f(GLES30.glGetUniformLocation(composite,"uSourceTexel"),1f/w.toFloat(),1f/h.toFloat())
        GLES30.glUniform1f(GLES30.glGetUniformLocation(composite,"uDiagnostic"),if(diagnostic)1f else 0f)'''
assert s.count(a)==1,(a,s.count(a))
s=s.replace(a,b,1)
p.write_text(s)
print("FSRCNNX learned residual now has edge-adaptive 5-sample anti-halo containment; film grain and chroma preserved")
