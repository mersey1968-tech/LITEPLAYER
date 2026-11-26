from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)
start=s.index("            float cubicNeural(vec2 pos)")
end=s.index("            void main(){",start)
s=s[:start]+"""            // Fixed fractional-delay FIR phases for exact 3:2 enlargement.
            // Constrained passband fit: DC gain and first moment preserved,
            // symmetric mirrored phases; non-cubic coefficients.
            vec3 phaseWeights(float f) {
                return f<0.3333333?vec3(-.082,-.057,.17442201):
                       f>0.6666667?vec3(-.057,-.082,.82557799):
                                      vec3(-.120,-.120,.5);
            }
            float polyphaseNeural(vec2 pos) {
                vec2 x=pos*uNeuralSize-.5;
                vec2 base=floor(x);
                vec2 f=fract(x);
                vec3 wx=phaseWeights(f.x),wy=phaseWeights(f.y);
                vec2 pt=1.0/uNeuralSize;
                vec2 c=(base+vec2(wx.z,wy.z)+.5)*pt;
                float m=texture(uNeural,c).r;
                float l=texture(uNeural,vec2((base.x-.5)*pt.x,c.y)).r;
                float r=texture(uNeural,vec2((base.x+2.5)*pt.x,c.y)).r;
                float b=texture(uNeural,vec2(c.x,(base.y-.5)*pt.y)).r;
                float t=texture(uNeural,vec2(c.x,(base.y+2.5)*pt.y)).r;
                // Cross-separable approximation: five reads rather than
                // nine; omit products of the small outer signed lobes.
                float y=m+dot(vec4(l-m,r-m,b-m,t-m),vec4(wx.xy,wy.xy));
                float lo=min(m,min(min(l,r),min(b,t)));
                float hi=max(m,max(max(l,r),max(b,t)));
                return clamp(y,lo-.012,hi+.012);
            }
"""+s[end:]
once("uCubicNeural>0.5?cubicNeural(uv):texture(uNeural,uv).r",
     "uCubicNeural>0.5?polyphaseNeural(uv):texture(uNeural,uv).r")
# Only use these coefficients at the exact trained fractional phases.
once("val cubic720=h <= 800 && outH > neural.h && outH >= 1600",
     "val cubic720=h <= 800 && outW*2 == neural.w*3 && outH*2 == neural.h*3")
# Reuse the original source cross samples from the preceding cleanup loop.
once("                float variation=0.;",
     "                float variation=0.;\n                vec4 sourceCross=vec4(0.);")
once("                    float delta=dot(abs(n-rawRgb),vec3(.25,.5,.25));",
     "                    sourceCross[i]=dot(n,vec3(0.2126,0.7152,0.0722));\n                    float delta=dot(abs(n-rawRgb),vec3(.25,.5,.25));")
once("""                    vec2 shift = i==0 ? sx : i==1 ? -sx : i==2 ? sy : -sy;
                    vec3 n=texture(uVideo,(uMatrix*vec4(uv+shift,0.,1.)).xy).rgb;
                    float l=dot(n,vec3(0.2126,0.7152,0.0722));""",
     "                    float l=sourceCross[i];")
p.write_text(s)
print("3:2 fixed-phase FIR, five learned reads; four duplicate decoder reads eliminated; other render stages unchanged")
