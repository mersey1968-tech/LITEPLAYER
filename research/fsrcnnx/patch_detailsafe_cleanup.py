"""Final assembled DetailSafe cleanup; preserve shader source, models and playback timing."""
from pathlib import Path
import re
import hashlib
root=Path("proj/app/src/main")
pkg=root/"java/com/example/liteplayer"
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
p=pkg/"ReferenceScalerView.kt"
s=p.read_text()
# The only caller supplies false; remove the obsolete experimental EGL path.
m=pkg/"MainActivity.kt"
main=m.read_text()
assert main.count("ReferenceScalerView(this, false)")==1
assert main.count("ReferenceScalerView(")==1
main=once(main,"ReferenceScalerView(this, false)","ReferenceScalerView(this)")
a=main.index("            gpu.onHdrUnavailable = {")
b=main.index("            scalerView = gpu",a)
main=main[:a]+main[b:]
# Old flag must be declaration-only after all preceding patches.
if len(re.findall(r"\breferenceHdrEnabled\b",main))==1:
    main=once(main,"    private var referenceHdrEnabled = false\n","")
m.write_text(main)
s=once(s,"context: Context, private val hdrRequested: Boolean = false","context: Context")
a=s.index("        if (hdrRequested) {")
b=s.index("        setRenderer(this)",a)
s=s[:a]+s[b:]
a=s.index("            if (hdrRequested && !hdrSurfaceActive) {")
b=s.index("            surfaceTexture = SurfaceTexture",a)
s=s[:a]+s[b:]
for name in ["hdrSurfaceActive","hdrConfigTenBit","onHdrUnavailable","hdrDiagnostic"]:
    s,n=re.subn(r"(?m)^    (?:@Volatile )?(?:private )?var "+name+r"\b[^\n]*\n","",s)
    assert n==1,name
    assert not re.search(r"\b"+name+r"\b",s),name
a=s.index("    private val vertices = ByteBuffer.allocateDirect(32)")
b=s.index("    init {",a)
s=s[:a]+s[b:]
# Removed by earlier patch: the methods which allocated these intermediates.
assert "ensureFramebuffer(" not in s
for name,decl in [("texIntermediate","    private var texIntermediate = 0\n"),("framebuffer","    private var framebuffer = 0\n"),("allocatedW","    private var allocatedW = 0\n"),("allocatedH","    private var allocatedH = 0\n")]:
    s=once(s,decl,"")
s=once(s,"; allocatedW = 0","")
for line in ["            if (texIntermediate!=0) GLES30.glDeleteTextures(1,intArrayOf(texIntermediate),0)\n","            if (framebuffer!=0) GLES30.glDeleteFramebuffers(1,intArrayOf(framebuffer),0)\n","            texIntermediate=0\n","            framebuffer=0\n"]:
    s=once(s,line,"")
for name in ["texIntermediate","framebuffer","allocatedW","allocatedH","hdrRequested"]:
    assert not re.search(r"\b"+name+r"\b",s),name
for imp in ["java.nio.ByteBuffer","java.nio.ByteOrder","javax.microedition.khronos.egl.EGL10","javax.microedition.khronos.egl.EGLDisplay","javax.microedition.khronos.egl.EGLSurface"]:
    s=once(s,"import "+imp+"\n","")
p.write_text(s)
# Pre-resolve each stage's producer version and uniform name once, avoiding
# a newly allocated name map and repeated string construction on every frame.
p=pkg/"FsrcnnxPipeline.kt"
s=p.read_text()
before=s
s=once(s,"    private val stages = mutableListOf<Stage>()","""    private val stages = mutableListOf<Stage>()
    private val inputProducers = mutableListOf<IntArray>()
    private val inputUniforms = mutableListOf<List<String>>()
    private fun resolveStageInputs() {
        val producers = HashMap<String, Int>()
        stages.forEachIndexed { idx, stage ->
            inputProducers.add(IntArray(stage.inputs.size) { unit ->
                val name = stage.inputs[unit]
                if (name == "LUMA") -1 else producers[name] ?: error("Missing network input "+name)
            })
            inputUniforms.add(stage.inputs.map { "u_"+it })
            producers[stage.output] = idx
        }
    }
""")
s=once(s,'        composite=link(vertexShader,','        resolveStageInputs()\n        composite=link(vertexShader,')
s=once(s,"        val named=mutableMapOf<String,Int>()\n","")
s=once(s,'val texture=if(name=="LUMA")video else named[name]?:error("Missing network input "+name)','val sourceIndex=inputProducers[idx][unit]\n                val texture=if(sourceIndex<0)video else targets[sourceIndex].texture')
s=once(s,'setUniform1i(stage.program,"u_"+name,unit)','setUniform1i(stage.program,inputUniforms[idx][unit],unit)')
s=once(s,'draw(stage.program);named[stage.output]=t.texture','draw(stage.program)')
assert not re.search(r'\bnamed\b',s)
# Every embedded GLSL string must stay byte-for-byte identical.
assert re.findall(r'"""(.*?)"""',before,re.S)==re.findall(r'"""(.*?)"""',s,re.S)
p.write_text(s)
asset=root/"assets/reflite/low_ringing_6tap.frag"
assert asset.is_file()
for source in root.rglob("*.kt"):
    assert "low_ringing_6tap.frag" not in source.read_text(),source
asset.unlink()
print("DetailSafe: obsolete SDR-to-HDR EGL experiment and unused legacy asset removed; stage lookup precomputed; GLSL unchanged.")
