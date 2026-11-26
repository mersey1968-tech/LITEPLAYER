from pathlib import Path
import re
root=Path("proj/app/src/main/java/com/example/liteplayer")
assets=Path("proj/app/src/main/assets/reflite")
# Convert only mpv host bindings to GLES. Preserve arithmetic and trained coefficients.
for name in ["ArtCNN","CuNNy"]:
    raw=(assets/(name+".glsl")).read_text()
    sections=re.split(r"(?=^//!DESC )",raw,flags=re.M)[1:]
    meta=[]
    for i,sec in enumerate(sections):
        binds=re.findall(r"^//!BIND (\w+)",sec,re.M)
        tile=list(map(int,re.search(r"^//!COMPUTE (.*)",sec,re.M)[1].split()))
        scale=int(float(re.search(r"^//!WIDTH LUMA.w ([\d.]+) \*",sec,re.M)[1]))
        output=re.search(r"^//!SAVE (\w+)",sec,re.M)
        output=output[1] if output else "FINAL"
        body=sec[sec.index("#extension"):]
        body=re.sub(r"#extension[^\n]*\n#ifdef[^\n]*\n.*?#endif\s*", "#define V4 vec4\n#define M4 mat4\n#define F float\n",body,count=1,flags=re.S)
        # GLES disallows nonconstant const initializers.
        body=re.sub(r"(?m)^([ \t]+)const ",r"\1",body)
        # Image writes outside partial workgroups must be suppressed, but
        # all threads still participate in the upstream shared-memory barrier.
        body=body.replace("imageStore(out_image,", "safeStore(")
        body=body.replace("void hook()", "void main()")
        header=f"#version 310 es\nprecision mediump float;\nprecision highp int;\nlayout(local_size_x={tile[2]},local_size_y={tile[3]}) in;\nlayout(rgba16f,binding=0) writeonly uniform highp image2D out_image;\nuniform highp ivec2 outputSize;\n"
        header+="void safeStore(highp ivec2 p,vec4 v){if(all(greaterThanEqual(p,ivec2(0)))&&all(lessThan(p,outputSize)))imageStore(out_image,p,v);}\n"
        for n in binds:
            # 'in' is reserved GLSL, so only use prefixed sampler identifiers.
            header+=f"uniform mediump sampler2D u_{n};\nuniform highp vec2 size_{n};\n#define {n}_raw u_{n}\n#define {n}_mul 1.0\n#define {n}_size size_{n}\n#define {n}_pt (1.0/size_{n})\n#define {n}_pos ((vec2(gl_GlobalInvocationID.xy)+0.5)/vec2(outputSize))\n#define {n}_tex(p) texture(u_{n},p)\n#define {n}_gather(p,c) textureGather(u_{n},p,c)\n"
        # ArtCNN's original texelFetch relies on host edge behavior;
        # clamp source coordinates explicitly without changing channel packing.
        header+="vec4 fetchEdge(sampler2D t,highp ivec2 p,int level){return texelFetch(t,clamp(p,ivec2(0),textureSize(t,level)-1),level);}\n"
        body=body.replace("texelFetch(","fetchEdge(")
        (assets/f"{name}-{i}.comp").write_text(header+body)
        meta.append(",".join([str(scale),str(tile[0]),str(tile[1]),output]+binds))
    (assets/(name+".stages")).write_text("\n".join(meta))
# Keep the existing player surface and colour reconstruction. New backend only.
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=s.replace("setEGLContextClientVersion(2)","setEGLContextClientVersion(3)")
# Insert fields using known final renderer constructor.
a="    private var neuralScale = 1.0f"
assert s.count(a)==1
s=s.replace(a,a+"\n    private var computePipeline: CurrentComputePipeline? = null")
# Replace selected neural draw; existing FSRCNNX stays as explicit failure fallback.
a="selected?.render(texVideo, transform, workW, workH, outW, outH,"
idx=s.index(a)
end=s.index(")",idx)+1
old=s[idx:end]
s=s[:idx]+'''if (computePipeline == null) {
                computePipeline = CurrentComputePipeline(context, if (maxMode) "CuNNy" else "ArtCNN")
            }
            computePipeline!!.render(texVideo, transform, workW, workH, outW, outH, !newFrame)'''+s[end:]
# Release on the owning GL thread alongside old pipelines.
a="            neural16Pipeline?.close()"
assert s.count(a)==1
s=s.replace(a,"            computePipeline?.close()\n            computePipeline=null\n"+a)
p.write_text(s)
p=root/"MainActivity.kt"
s=p.read_text().replace('"FSRCNNX Neural (SDR)", "Max"','"ArtCNN C4F16-DS", "CuNNy-4x16-DS"')
p.write_text(s)
