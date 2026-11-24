"""Reflite FSRCNNX: dependency-aware intermediate framebuffer reuse.

Preserves 26 shader stages, every sample and shader instruction, RGBA16F
precision, final cubic filtering, all uniforms, original frame timing and
neural quality. Uses distinct FBO/texture allocations only for concurrently
live model values. A value's physical target is recycled ONLY after the
last shader stage that reads its version has completed.

The model reuses logical feature names (MODEL1 etc.); last-use analysis
therefore tracks PRODUCER STAGE VERSIONS, not just feature names.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
old='''    private fun ensureSize(w:Int,h:Int) {
        if(w==allocatedW && h==allocatedH)return
        releaseTargets();allocatedW=w;allocatedH=h
        stages.forEach { targets.add(allocate(if(it.scaled)2*w else w,if(it.scaled)2*h else h)) }
        // Cubic reconstruction relies on bilinear 2x2 blending for its
        // four-fetch optimization. Only the final learned luma texture needs it.
        targets.lastOrNull()?.let {
            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,it.texture)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MIN_FILTER,GLES30.GL_LINEAR)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MAG_FILTER,GLES30.GL_LINEAR)
        }
    }'''
new='''    private fun ensureSize(w:Int,h:Int) {
        if(w==allocatedW && h==allocatedH)return
        releaseTargets();allocatedW=w;allocatedH=h
        // Resolve producer versions first: model hook names are overwritten
        // by later layers, so name-only lifetime tracking is unsafe.
        val producer=mutableMapOf<String,Int>()
        val lastRead=IntArray(stages.size){ it }
        stages.forEachIndexed { idx,stage ->
            stage.inputs.forEach { name ->
                if (name != "LUMA") {
                    val source = producer[name] ?: error("Missing neural input " + name)
                    lastRead[source] = idx
                }
            }
            producer[stage.output] = idx
        }
        // Final learned luma remains live through the separate composite draw.
        lastRead[lastRead.lastIndex] = stages.size
        val free=mutableListOf<Target>()
        var reused=0
        stages.forEachIndexed { idx,stage ->
            // Previous stage's framebuffer output is now safe to reuse only
            // if no FUTURE shader reads its contents. Never use an input
            // texture simultaneously as this stage's render attachment.
            if (idx>0) for (prior in 0 until idx) {
                if (lastRead[prior] == idx-1) free.add(targets[prior])
            }
            val tw=if(stage.scaled) 2*w else w
            val th=if(stage.scaled) 2*h else h
            val existing=free.indexOfFirst { it.w==tw && it.h==th }
            val target=if(existing>=0) {
                reused++
                free.removeAt(existing)
            } else allocate(tw,th)
            targets.add(target)
        }
        android.util.Log.i("Reflite GPU", "Neural FBO reuse: stages=" +
            stages.size + " allocations=" + targets.map{it.texture}.distinct().size +
            " reused=" + reused + " inference=" + w + "x" + h)
        // Preserve the original final texture's GL_LINEAR filter for the
        // exact same four-tap cubic final reconstruction.
        targets.lastOrNull()?.let {
            GLES30.glBindTexture(GLES30.GL_TEXTURE_2D,it.texture)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MIN_FILTER,GLES30.GL_LINEAR)
            GLES30.glTexParameteri(GLES30.GL_TEXTURE_2D,GLES30.GL_TEXTURE_MAG_FILTER,GLES30.GL_LINEAR)
        }
    }'''
assert s.count(old)==1, "ensureSize anchor changed; abort rather than risk a PQ regression"
s=s.replace(old,new,1)
old='''    private fun releaseTargets(){
        targets.forEach {
            GLES30.glDeleteTextures(1,intArrayOf(it.texture),0)
            GLES30.glDeleteFramebuffers(1,intArrayOf(it.fbo),0)
        }
        targets.clear()
    }'''
new='''    private fun releaseTargets(){
        // Multiple stage outputs can now refer to the same physical target.
        // Delete each physical allocation exactly once.
        targets.distinctBy{it.texture}.forEach {
            GLES30.glDeleteTextures(1,intArrayOf(it.texture),0)
            GLES30.glDeleteFramebuffers(1,intArrayOf(it.fbo),0)
        }
        targets.clear()
    }'''
assert s.count(old)==1, "releaseTargets anchor changed"
s=s.replace(old,new,1)
p.write_text(s)
print("Reflite GPU FBO reuse staged: same neural shaders, RGBA16F, original filter, timing, RGB composition.")
