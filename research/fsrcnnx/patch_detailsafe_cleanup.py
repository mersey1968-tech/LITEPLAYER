"""Final assembled DetailSafe cleanup; preserve shader source, models and playback timing."""
from pathlib import Path
import re
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
    private val inputLocations = mutableListOf<IntArray>()
    private val sizeLocations = mutableListOf<Int>()
    private val matrixLocations = mutableListOf<Int>()
    private val drawLocations = mutableListOf<Int>()
    private fun resolveStageInputs() {
        val producers = HashMap<String, Int>()
        stages.forEachIndexed { idx, stage ->
            inputProducers.add(IntArray(stage.inputs.size) { unit ->
                val name = stage.inputs[unit]
                if (name == "LUMA") -1 else producers[name] ?: error("Missing network input "+name)
            })
            inputLocations.add(IntArray(stage.inputs.size) { unit -> uniformLocation(stage.program, "u_"+stage.inputs[unit]) })
            sizeLocations.add(uniformLocation(stage.program, "uSize"))
            matrixLocations.add(if ("LUMA" in stage.inputs) uniformLocation(stage.program, "uMatrix") else -1)
            drawLocations.add(attributeLocation(stage.program))
            producers[stage.output] = idx
        }
    }
""")
s=once(s,'        composite=link(vertexShader,','        resolveStageInputs()\n        composite=link(vertexShader,')
s=once(s,"        val named=mutableMapOf<String,Int>()\n","")
s=once(s,'val texture=if(name=="LUMA")video else named[name]?:error("Missing network input "+name)','val sourceIndex=inputProducers[idx][unit]\n                val texture=if(sourceIndex<0)video else targets[sourceIndex].texture')
s=once(s,'setUniform1i(stage.program,"u_"+name,unit)','if (changed(stage.program,inputLocations[idx][unit],unit.toLong())) GLES30.glUniform1i(inputLocations[idx][unit],unit)')
s=once(s,'draw(stage.program);named[stage.output]=t.texture','draw(stage.program)')
assert not re.search(r'\bnamed\b',s)
s=once(s,'setUniform2f(stage.program,"uSize",w.toFloat(),h.toFloat())',"""val sizeBits=(w.toFloat().toRawBits().toLong() shl 32) or (h.toFloat().toRawBits().toLong() and 0xffffffffL)
            if (changed(stage.program,sizeLocations[idx],sizeBits))
                GLES30.glUniform2f(sizeLocations[idx],w.toFloat(),h.toFloat())""")
s=once(s,'uniformLocation(stage.program,"uMatrix")','matrixLocations[idx]')
# Scope binding cache to a single inference: no assumptions about other renderers.
s=once(s,'        var viewportW = -1','''        var activeUnit = -1
        val bound2D = IntArray(maxInputUnits) { -1 }
        val boundExternal = IntArray(maxInputUnits) { -1 }
        var viewportW = -1''')
s=once(s,'    private val inputProducers = mutableListOf<IntArray>()','    private val inputProducers = mutableListOf<IntArray>()\n    private var maxInputUnits = 1')
s=once(s,'            inputProducers.add(IntArray(stage.inputs.size)', '            maxInputUnits = maxOf(maxInputUnits,stage.inputs.size)\n            inputProducers.add(IntArray(stage.inputs.size)')
s=once(s,'''                GLES30.glActiveTexture(GLES30.GL_TEXTURE0+unit)
                GLES30.glBindTexture(if(name=="LUMA")GLES11Ext.GL_TEXTURE_EXTERNAL_OES else GLES30.GL_TEXTURE_2D,texture)''','''                val bindings=if(sourceIndex<0)boundExternal else bound2D
                if (bindings[unit]!=texture) {
                    if (activeUnit!=unit) {
                        GLES30.glActiveTexture(GLES30.GL_TEXTURE0+unit)
                        activeUnit=unit
                    }
                    GLES30.glBindTexture(if(sourceIndex<0)GLES11Ext.GL_TEXTURE_EXTERNAL_OES else GLES30.GL_TEXTURE_2D,texture)
                    bindings[unit]=texture
                }''')
# Draw attribute locations are immutable for linked programs.
s=once(s,'private fun draw(program:Int) {','private fun draw(program:Int, cachedLocation:Int = -1) {')
s=once(s,'val loc=attributeLocation(program)','val loc=if(cachedLocation>=0)cachedLocation else attributeLocation(program)')
s=once(s,'draw(stage.program)','draw(stage.program,drawLocations[idx])')


# Persistent geometry: identical 8 floats, same triangle strip and attribute
# layout. One VAO per attribute location, local to this GL context.
s=once(s,"    private var composite=0","""    private var composite=0
    private var geometryBuffer=0
    private val geometryVaos=HashMap<Int,Int>()
    private fun prepareGeometry() {
        val ids=IntArray(1)
        GLES30.glGenBuffers(1,ids,0)
        geometryBuffer=ids[0]
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER,geometryBuffer)
        vertices.position(0)
        GLES30.glBufferData(GLES30.GL_ARRAY_BUFFER,32,vertices,GLES30.GL_STATIC_DRAW)
        for (loc in (drawLocations+attributeLocation(composite)).distinct()) {
            check(loc>=0)
            GLES30.glGenVertexArrays(1,ids,0)
            geometryVaos[loc]=ids[0]
            GLES30.glBindVertexArray(ids[0])
            GLES30.glEnableVertexAttribArray(loc)
            GLES30.glVertexAttribPointer(loc,2,GLES30.GL_FLOAT,false,0,0)
        }
        GLES30.glBindVertexArray(0)
        GLES30.glBindBuffer(GLES30.GL_ARRAY_BUFFER,0)
    }
    private val uploadedMatrices=HashMap<Int,FloatArray>()
    private fun uploadMatrix(program:Int,location:Int,matrix:FloatArray) {
        if(location<0)return
        val previous=uploadedMatrices[program]
        if(previous==null || !previous.contentEquals(matrix)) {
            GLES30.glUniformMatrix4fv(location,1,false,matrix,0)
            if(previous==null) uploadedMatrices[program]=matrix.copyOf()
            else matrix.copyInto(previous)
        }
    }
    private lateinit var cached2D:IntArray
    private lateinit var cachedExternal:IntArray
""")
s=once(s,'        """)\n    }\n    private fun link','        """)\n        prepareGeometry()\n        cached2D=IntArray(maxInputUnits)\n        cachedExternal=IntArray(maxInputUnits)\n    }\n    private fun link')
s=once(s,'''        vertices.position(0);GLES30.glEnableVertexAttribArray(loc)
        GLES30.glVertexAttribPointer(loc,2,GLES30.GL_FLOAT,false,0,vertices)
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP,0,4)
        GLES30.glDisableVertexAttribArray(loc)''','''        GLES30.glBindVertexArray(geometryVaos.getValue(loc))
        GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP,0,4)
        GLES30.glBindVertexArray(0)''')
s=once(s,'val bound2D = IntArray(maxInputUnits) { -1 }','val bound2D = cached2D.apply { fill(-1) }')
s=once(s,'val boundExternal = IntArray(maxInputUnits) { -1 }','val boundExternal = cachedExternal.apply { fill(-1) }')
s=once(s,'GLES30.glUniformMatrix4fv(matrixLocations[idx],1,false,matrix,0)','uploadMatrix(stage.program,matrixLocations[idx],matrix)')
s=once(s,'GLES30.glUniformMatrix4fv(uniformLocation(composite,"uMatrix"),1,false,matrix,0)','uploadMatrix(composite,uniformLocation(composite,"uMatrix"),matrix)')
s=once(s,'    fun close(){','''    fun close(){
        geometryVaos.values.forEach { GLES30.glDeleteVertexArrays(1,intArrayOf(it),0) }
        geometryVaos.clear()
        GLES30.glDeleteBuffers(1,intArrayOf(geometryBuffer),0)
        uploadedMatrices.clear()''')
# Protect original sync correction at the final assembled source boundary.
assert 'val distance = (6000.0 / fps).toLong().coerceAtLeast(1L)' in main
assert 'activePlayer.seekTo(position - distance)' in main

# Every embedded GLSL string must stay byte-for-byte identical.
assert re.findall(r'"""(.*?)"""',before,re.S)==re.findall(r'"""(.*?)"""',s,re.S)
p.write_text(s)
asset=root/"assets/reflite/low_ringing_6tap.frag"
assert asset.is_file()
for source in root.rglob("*.kt"):
    assert "low_ringing_6tap.frag" not in source.read_text(),source
asset.unlink()
print("DetailSafe: obsolete SDR-to-HDR EGL experiment and unused legacy asset removed; stage lookup precomputed; GLSL unchanged.")
