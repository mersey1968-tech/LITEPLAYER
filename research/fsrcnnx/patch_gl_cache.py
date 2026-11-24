"""Reduce 1080p CPU-side GLES overhead without changing image math or pacing policy."""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
anchor="    private val stages = mutableListOf<Stage>()"
assert s.count(anchor)==1
# Rewrite only the existing render and draw lookups, before adding helpers.
assert s.count("GLES30.glGetUniformLocation(")>=10
s=s.replace("GLES30.glGetUniformLocation(", "uniformLocation(")
assert s.count('GLES30.glGetAttribLocation(program,"position")')==1
s=s.replace('GLES30.glGetAttribLocation(program,"position")','attributeLocation(program)')
s=s.replace(anchor,anchor+"""
    // Locations remain valid for the lifetime of each linked program.
    // Per-pipeline cache, used only on its owning GL thread.
    private val uniformLocations = HashMap<Int, HashMap<String, Int>>()
    private val attributeLocations = HashMap<Int, Int>()
    private fun uniformLocation(program: Int, name: String): Int =
        uniformLocations.getOrPut(program) { HashMap() }.getOrPut(name) {
            GLES30.glGetUniformLocation(program, name)
        }
    private fun attributeLocation(program: Int): Int =
        attributeLocations.getOrPut(program) {
            GLES30.glGetAttribLocation(program, "position")
        }
""",1)
# Within a single inference call, avoid repeated viewports. Do not cache
# global state across calls: SurfaceTexture and other passes can alter it.
a="        stages.forEachIndexed { idx,stage ->\n            val t=targets[idx]"
assert s.count(a)==1
s=s.replace(a,"""        var viewportW = -1
        var viewportH = -1
        stages.forEachIndexed { idx,stage ->
            val t=targets[idx]""",1)
a="            GLES30.glViewport(0,0,t.w,t.h)"
assert s.count(a)==1
s=s.replace(a,"""            if (viewportW != t.w || viewportH != t.h) {
                GLES30.glViewport(0,0,t.w,t.h)
                viewportW = t.w
                viewportH = t.h
            }""",1)
p.write_text(s)
print("Cached shader locations and redundant viewport elimination; shaders, precision, GPU timing and scaling thresholds unchanged.")
