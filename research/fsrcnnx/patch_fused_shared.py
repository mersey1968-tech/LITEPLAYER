from pathlib import Path
import re
assets=Path("proj/app/src/main/assets/reflite")
raw=(assets/"FSRCNNX_x2_8-0-4-1.glsl").read_text()
sections=raw.split("//!HOOK ")[1:]
assert len(sections)==14
# 16x16 output source pixels, 7-pixel receptive radius.
# Shared feature buffers are explicitly half-packed even on drivers
# which implement mediump shared variables as 32-bit storage.
N=16
S=N+14
# Use 8x8 output tile to bound shared storage; 22x22 input.
N=8; S=N+14
header=f"""#version 310 es
precision mediump float;
precision highp int;
layout(local_size_x=8,local_size_y=8) in;
layout(rgba16f,binding=0) writeonly uniform highp image2D out_image;
uniform highp sampler2D u_LUMA;
uniform highp vec2 size_LUMA;
uniform highp ivec2 outputSize;
const int N={N}, S={S};
shared highp uint a[{S*S*4}], b[{S*S*4}];
shared highp uint skip[{S*S*4}];
shared mediump float ytile[{S*S}];
int ix(ivec2 p){{return p.y*S+p.x;}}
vec4 readA(ivec2 p,int c){{int i=4*ix(p)+2*c;return vec4(unpackHalf2x16(a[i]),unpackHalf2x16(a[i+1]));}}
vec4 readB(ivec2 p,int c){{int i=4*ix(p)+2*c;return vec4(unpackHalf2x16(b[i]),unpackHalf2x16(b[i+1]));}}
vec4 readSkip(ivec2 p,int c){{int i=4*ix(p)+2*c;return vec4(unpackHalf2x16(skip[i]),unpackHalf2x16(skip[i+1]));}}
void writeA(ivec2 p,int c,vec4 v){{int i=4*ix(p)+2*c;a[i]=packHalf2x16(v.xy);a[i+1]=packHalf2x16(v.zw);}}
void writeB(ivec2 p,int c,vec4 v){{int i=4*ix(p)+2*c;b[i]=packHalf2x16(v.xy);b[i+1]=packHalf2x16(v.zw);}}
void writeSkip(ivec2 p,int c,vec4 v){{int i=4*ix(p)+2*c;skip[i]=packHalf2x16(v.xy);skip[i+1]=packHalf2x16(v.zw);}}
"""
# Every stage is generated verbatim except texture reads. At picture edges
# each intermediate stage clamps its logical source coordinate, as mpv does.
functions=[]
names={}
for i,sec in enumerate(sections[:13]):
    body="vec4 "+f"layer{i}(ivec2 p)"+sec.split("vec4 hook()",1)[1]
    binds=re.findall(r"//!BIND (\w+)",sec)
    if i<2:
        def fetch(m):return "ytile[ix(p+ivec2("+m[1]+"))]"
        body=re.sub(r"LUMA_texOff\(vec2\(([-\d, ]+)\)\)",fetch,body)
    else:
        for name in binds:
            arr,c=names[name]
            body=re.sub(rf"{name}_texOff\(vec2\(([-\d, ]+)\)\)",lambda m:f"read{arr}(p+ivec2({m[1]}),{c})",body)
            body=body.replace(name+"_texOff(0)",f"read{arr}(p,{c})")
    assert "_texOff" not in body
    functions.append(body)
    save=re.search(r"//!SAVE (\w+)",sec)[1]
    if i<2: names[save]=("Skip",i)
    elif i<10: names[save]=("B" if (i//2)%2 else "A",i%2)
    elif i<12: names[save]=("B" if (i//2)%2 else "A",i%2)
# Layer 2/3 reads Skip, layer 4/5 reads B, etc. Residual reads B, writes A.
# First feature extraction is written to Skip only. Mapping 1 -> B.
# At edges do not duplicate feature coordinates within the tile; instead
# compute each logical intermediate at its clamped global position and
# shift its local read origin accordingly.
main="""void main(){
ivec2 base=ivec2(gl_WorkGroupID.xy)*N-ivec2(7);
ivec2 lim=ivec2(size_LUMA)-1;
int tid=int(gl_LocalInvocationIndex);
for(int j=tid;j<S*S;j+=64){
 ivec2 p=ivec2(j%S,j/S);
 ytile[j]=texelFetch(u_LUMA,clamp(base+p,ivec2(0),lim),0).r;
}
barrier();
"""
# For feature extraction p outside the frame, clamp the convolution center;
# intermediate data is available at the clamped coordinate inside tile.
# For partial tiles with no valid centers in an outer region, guard the
# shift to the initialized region. In-range pixels' dependency cones
# never require any value outside that region.
for i in range(0,12,2):
    radius=2+i//2 if i<10 else 6
    arr="Skip" if i==0 else ("B" if (i//2)%2 else "A")
    width=S-2*radius
    main+=f"""
for(int j=tid;j<{width*width};j+=64){{
 ivec2 p=ivec2(j%{width},j/{width})+ivec2({radius});
 ivec2 q=clamp(clamp(base+p,ivec2(0),lim)-base,ivec2({radius}),ivec2(S-1-{radius}));
 vec4 v0=layer{i}(q),v1=layer{i+1}(q);
 write{arr}(p,0,v0);write{arr}(p,1,v1);
}}
barrier();
"""
# Final subpixel convolution and x-major ordering from original model.
main+="""
ivec2 p=ivec2(gl_LocalInvocationID.xy)+ivec2(7);
ivec2 g=base+p;
if(all(lessThanEqual(g,lim))){
 vec4 v=layer12(p);
 float lo=1.0,hi=0.0;
 for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
  float y=ytile[ix(p+ivec2(i,j))];lo=min(lo,y);hi=max(hi,y);
 }
 v=clamp(v,vec4(lo-0.02),vec4(hi+0.02));
 for(int x=0;x<2;x++)for(int y=0;y<2;y++){
  imageStore(out_image,g*2+ivec2(x,y),vec4(v[x*2+y],0.,0.,1.));
 }
}
}
"""
# Actual packed arrays: 3*22*22*16 + 22*22*4 = 25168 bytes.
(assets/"Fused-0.comp").write_text(header+"\n".join(functions)+main)
(assets/"Fused.stages").write_text("2,16,16,FINAL,LUMA\n")
print("Generated 13 original trained stages fused into one dispatch; 25168-byte conservative shared-memory footprint")
# Switch both former modes to a single fused selection (second mode removed).
root=Path("proj/app/src/main/java/com/example/liteplayer")
p=root/"ReferenceScalerView.kt"
s=p.read_text().replace('if (maxMode) "CuNNy" else "ArtCNN"','"Fused"')
p.write_text(s)
p=root/"MainActivity.kt"
s=p.read_text().replace('"ArtCNN C4F16-DS", "CuNNy-4x16-DS"','"Fused FSRCNNX"')
p.write_text(s)
p=root/"CurrentComputePipeline.kt"
s=p.read_text().replace('check(stages.size==if(model=="ArtCNN") 8 else 6)','check(stages.size==1)')
p.write_text(s)
