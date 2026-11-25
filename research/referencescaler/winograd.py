"""Replace ArtCNN middle convolutions with F(2,3), retaining original coefficients."""
import re, math, random
from pathlib import Path
G=((1,0,0),(.5,.5,.5),(.5,-.5,.5),(0,0,1))
B=((1,0,-1,0),(0,1,1,0),(0,-1,1,0),(0,1,0,-1))
A=((1,1,1,0),(0,1,-1,-1))
def trans(m,x):
    return [[sum(m[i][k]*x[k][l]*m[j][l] for k in range(len(x)) for l in range(len(x))) for j in range(len(m))] for i in range(len(m))]
# Validate the transform including orientation before generating shader.
random.seed(42)
for _ in range(20):
    d=[[random.random() for x in range(4)] for y in range(4)]
    k=[[random.random() for x in range(3)] for y in range(3)]
    u,v=trans(G,k),trans(B,d)
    y=trans(A,[[u[i][j]*v[i][j] for j in range(4)] for i in range(4)])
    assert max(abs(y[i][j]-sum(d[i+a][j+b]*k[a][b] for a in range(3) for b in range(3))) for i in range(2) for j in range(2))<1e-10
assets=Path("proj/app/src/main/assets/reflite")
for n in range(1,6):
    p=assets/f"art{n}.comp"
    s=p.read_text()
    weights={}
    for o,vals,ig,x,y in re.findall(r"result(\d) \+= M4\(([^)]+)\) \* inp_(\d)_(\d)_(\d);",s):
        weights[int(o),int(ig),2-int(y),int(x)]=[float(v) for v in vals.split(",")]
    assert len(weights)==144
    bias=dict((int(o),v) for o,v in re.findall(r"V4 result(\d) = V4\(([^)]+)\);",s))
    assert len(bias)==4
    # Each invocation computes one 2x2 spatial tile and one output vec4.
    # Shared tile transforms reused by all four output feature groups.
    lines=["#version 310 es","precision highp float; precision highp int;",
    "layout(local_size_x=4,local_size_y=4,local_size_z=4) in;",
    "layout(rgba16f,binding=0) writeonly uniform highp image2D out_image;",
    "uniform highp sampler2D sourceTex; uniform ivec2 size;",
    "shared vec4 V[16][4][16];",
    "void main(){",
    "ivec2 tile=ivec2(gl_GlobalInvocationID.xy); int g=int(gl_LocalInvocationID.z); int lane=int(gl_LocalInvocationID.y)*4+int(gl_LocalInvocationID.x);",
    "vec4 d[16]; vec4 t[16];",
    "for(int y=0;y<4;y++)for(int x=0;x<4;x++){ivec2 q=clamp(tile*2+ivec2(x-1,y-1),ivec2(0),size-1);d[y*4+x]=texelFetch(sourceTex,q*2+ivec2(g%2,g/2),0);}",
    "for(int i=0;i<4;i++){t[i]=d[i]-d[8+i];t[4+i]=d[4+i]+d[8+i];t[8+i]=d[8+i]-d[4+i];t[12+i]=d[4+i]-d[12+i];}",
    "for(int i=0;i<4;i++){int j=4*i;V[lane][g][j]=t[j]-t[j+2];V[lane][g][j+1]=t[j+1]+t[j+2];V[lane][g][j+2]=t[j+2]-t[j+1];V[lane][g][j+3]=t[j+1]-t[j+3];}",
    "barrier();","vec4 m[16];"]
    # Branch by output group, constants compiled into separate code paths.
    for o in range(4):
        lines.append(("if" if o==0 else "else if")+f"(g=={o})"+"{")
        for i in range(16):
            y,x=divmod(i,4)
            terms=[]
            for ig in range(4):
                vals=[sum(G[y][a]*weights[o,ig,a,b][c]*G[x][b] for a in range(3) for b in range(3)) for c in range(16)]
                fmt=lambda z: format(z,'.9e')
                terms.append("mat4("+",".join(map(fmt,vals))+f")*V[lane][{ig}][{i}]")
            lines.append(f"m[{i}]="+"+".join(terms)+";")
        lines.append("}")
    lines+=["vec4 a[8];for(int i=0;i<4;i++){a[i]=m[i]+m[4+i]+m[8+i];a[4+i]=m[4+i]-m[8+i]-m[12+i];}",
    "vec4 b=vec4(0.);"]
    for o in range(4):lines.append(f"if(g=={o})b=vec4({bias[o]});")
    lines+=["for(int y=0;y<2;y++)for(int x=0;x<2;x++){int j=y*4;vec4 r=b+(x==0?a[j]+a[j+1]+a[j+2]:a[j+1]-a[j+2]-a[j+3]);ivec2 q=tile*2+ivec2(x,y);if(all(lessThan(q,size)))imageStore(out_image,q*2+ivec2(g%2,g/2),"+("max(r,vec4(0.))" if n<5 else "r")+");}","}"]
    p.write_text("\n".join(lines))
print("Winograd transforms verified; five middle layers replaced")
