"""Reuse valid neural inference on duplicate draws and cache scalar uniforms.
No shader, frame timing, or resolution policy changes."""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
# Scope cache by program and uniform location, including all scalar values.
# A program is never relinked during its pipeline lifetime.
s=s.replace("GLES30.glUniform1i(uniformLocation(", "setUniform1i(")
s=s.replace("GLES30.glUniform1f(uniformLocation(", "setUniform1f(")
s=s.replace("GLES30.glUniform2f(uniformLocation(", "setUniform2f(")
import re
s=re.sub(r'(setUniform[12][if]\([^\n]*?),("(?:u_|u)[^"\n]*"(?:\+name)?)\),',r'\1,\2,',s)
# Verify every rewritten call lost the inner closing parenthesis.
for line in s.splitlines():
    if "setUniform" in line:
        assert line.count("(")==line.count(")"),line
anchor="    private val stages = mutableListOf<Stage>()"
s=once(s,anchor,anchor+"""
    private val scalarUniforms = HashMap<Int, HashMap<Int, Long>>()
    private fun changed(program: Int, loc: Int, bits: Long): Boolean {
        if (loc < 0) return false
        return scalarUniforms.getOrPut(program) { HashMap() }.put(loc, bits) != bits
    }
    private fun setUniform1i(program: Int, name: String, x: Int) {
        val loc = uniformLocation(program, name)
        if (changed(program, loc, x.toLong())) GLES30.glUniform1i(loc, x)
    }
    private fun setUniform1f(program: Int, name: String, x: Float) {
        val loc = uniformLocation(program, name)
        if (changed(program, loc, x.toRawBits().toLong())) GLES30.glUniform1f(loc, x)
    }
    private fun setUniform2f(program: Int, name: String, x: Float, y: Float) {
        val loc = uniformLocation(program, name)
        val bits = (x.toRawBits().toLong() shl 32) or (y.toRawBits().toLong() and 0xffffffffL)
        if (changed(program, loc, bits)) GLES30.glUniform2f(loc, x, y)
    }
    private var inferenceValid = false
    private var inferenceVideo = -1
    private val inferenceMatrix = FloatArray(16)
""")
# Retain the final dedicated neural texture; rerun composite on every draw,
# so output surface resize and diagnostics changes still appear correctly.
s=once(s,"originalFrameHeight:Int=h) {","originalFrameHeight:Int=h, reuseInference:Boolean=false) {")
s=once(s,"        ensureSize(w,h);val named=mutableMapOf<String,Int>()","""        val canReuse = reuseInference && inferenceValid && allocatedW == w &&
            allocatedH == h && inferenceVideo == video && inferenceMatrix.contentEquals(matrix)
        ensureSize(w,h)
        if (!canReuse) {
        val named=mutableMapOf<String,Int>()""")
s=once(s,"        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,outputFbo)","""        inferenceValid = true
        inferenceVideo = video
        matrix.copyInto(inferenceMatrix)
        }
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,outputFbo)""")
s=once(s,"    private fun releaseTargets(){","    private fun releaseTargets(){\n        inferenceValid = false")
p.write_text(s)
p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
s=once(s,"diagnosticEnabled, false, originalFrameHeight=srcH)","diagnosticEnabled, false, originalFrameHeight=srcH, reuseInference=!newFrame)")
p.write_text(s)
print("Duplicate inference reuse and scalar uniform caching staged.")
