from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
def once(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)
once("    private val stages = mutableListOf<Stage>()", """    private val stages = mutableListOf<Stage>()
    private data class MrtGroup(val start:Int,val program:Int,val inputs:List<String>,val producers:IntArray)
    private val mrtGroups=HashMap<Int,MrtGroup>()
    private val mrtFbo=IntArray(1)
    private fun prepareMrt(raw:String) {
        if (!maxMode) return
        val caps=IntArray(1)
        GLES30.glGetIntegerv(GLES30.GL_MAX_DRAW_BUFFERS,caps,0)
        if(caps[0]<4)return
        GLES30.glGetIntegerv(GLES30.GL_MAX_COLOR_ATTACHMENTS,caps,0)
        if(caps[0]<4)return
        val sections=raw.split("//!HOOK ").drop(1)
        if(sections.size!=26)return
        val built=mutableListOf<MrtGroup>()
        try {
            for(start in 0 until 24 step 4) {
                val batch=stages.subList(start,start+4)
                check(batch.none{it.scaled})
                val inputs=batch.flatMap{it.inputs}.distinct()
                val producers=IntArray(inputs.size){ i ->
                    if(inputs[i]=="LUMA") -1
                    else (start-1 downTo 0).first{stages[it].output==inputs[i]}
                }
                check(batch.none{stage -> stage.inputs.any{n -> batch.any{it.output==n}}})
                val defs=StringBuilder()
                for(n in inputs) {
                    if(n=="LUMA") {
                        defs.append("uniform samplerExternalOES u_LUMA;uniform mat4 uMatrix;\\n")
                        defs.append("float LUMA_texOff(vec2 d){vec3 c=texture(u_LUMA,(uMatrix*vec4(uv+d/uSize,0.,1.)).xy).rgb;return dot(c,vec3(.2126,.7152,.0722));}\\n")
                    } else {
                        defs.append("uniform sampler2D u_").append(n).append(";\\n")
                        defs.append("vec4 ").append(n).append("_texOff(vec2 d){return texture(u_").append(n).append(",uv+d/uSize);}\\n")
                        defs.append("vec4 ").append(n).append("_texOff(int n){return texture(u_").append(n).append(",uv);}\\n")
                    }
                }
                val samplePattern=Regex("[A-Z][A-Z0-9]*_texOff[(](vec2[(]-?[0-9]+,-?[0-9]+[)]|0)[)]")
                val bodies=(0..3).map{ k ->
                    sections[start+k].substringAfter("vec4 hook()").trim()
                        .removePrefix("{").trim().removeSuffix("}").trim()
                }
                val samples=bodies.flatMap{b -> samplePattern.findAll(b).map{it.value}.toList()}.distinct()
                val locals=samples.withIndex().associate{it.value to "tap"+it.index}
                val source=StringBuilder("#version 300 es\\n")
                if("LUMA" in inputs)source.append("#extension GL_OES_EGL_image_external_essl3 : require\\n")
                source.append("precision highp float;in vec2 uv;uniform vec2 uSize;\\n")
                source.append(defs)
                for(k in 0..3)source.append("layout(location="+k+") out vec4 result"+k+";\\n")
                source.append("void main(){\\n")
                for(sample in samples)source.append((if(sample.startsWith("LUMA_"))"float " else "vec4 ")+locals.getValue(sample)+"="+sample+";\\n")
                for(k in 0..3) {
                    val body=samplePattern.replace(bodies[k]){locals.getValue(it.value)}
                        .replace("return res;","result"+k+"=res;")
                    source.append("{\\n"+body+"\\n}\\n")
                }
                source.append("}\\n")
                built.add(MrtGroup(start,link(vertexShader,source.toString()),inputs,producers))
            }
            GLES30.glGenFramebuffers(1,mrtFbo,0)
            check(mrtFbo[0]!=0)
            built.forEach{mrtGroups[it.start]=it}
        } catch(e:Throwable) {
            built.forEach{GLES30.glDeleteProgram(it.program)}
            mrtGroups.clear()
        }
    }
    private fun drawMrt(g:MrtGroup,video:Int,matrix:FloatArray,w:Int,h:Int) {
        GLES30.glBindFramebuffer(GLES30.GL_FRAMEBUFFER,mrtFbo[0])
        val attachments=IntArray(4){GLES30.GL_COLOR_ATTACHMENT0+it}
        for(k in 0..3)GLES30.glFramebufferTexture2D(GLES30.GL_FRAMEBUFFER,attachments[k],GLES30.GL_TEXTURE_2D,targets[g.start+k].texture,0)
        GLES30.glDrawBuffers(4,attachments,0)
        check(GLES30.glCheckFramebufferStatus(GLES30.GL_FRAMEBUFFER)==GLES30.GL_FRAMEBUFFER_COMPLETE)
        GLES30.glViewport(0,0,w,h)
        GLES30.glUseProgram(g.program)
        setUniform2f(g.program,"uSize",w.toFloat(),h.toFloat())
        for(k in g.inputs.indices) {
            val producer=g.producers[k]
            GLES30.glActiveTexture(GLES30.GL_TEXTURE0+k)
            GLES30.glBindTexture(if(producer<0)GLES11Ext.GL_TEXTURE_EXTERNAL_OES else GLES30.GL_TEXTURE_2D,if(producer<0)video else targets[producer].texture)
            setUniform1i(g.program,"u_"+g.inputs[k],k)
        }
        if("LUMA" in g.inputs)uploadMatrix(g.program,uniformLocation(g.program,"uMatrix"),matrix)
        draw(g.program)
    }
""")
once("        prepareGeometry()", "        prepareMrt(raw)\n        prepareGeometry()")
once("(drawLocations+attributeLocation(composite)).distinct()", "(drawLocations+attributeLocation(composite)+mrtGroups.values.map{attributeLocation(it.program)}).distinct()")
once("val existing=if (idx == stages.lastIndex) -1 else free.indexOfFirst", "val existing=if (mrtGroups.isNotEmpty() || idx == stages.lastIndex) -1 else free.indexOfFirst")
once("        stages.forEachIndexed { idx,stage ->\n            val t=targets[idx]", """        stages.forEachIndexed { idx,stage ->
            if(mrtGroups.isNotEmpty() && idx<24) {
                mrtGroups[idx]?.let{drawMrt(it,video,matrix,w,h)}
                bound2D.fill(-1);boundExternal.fill(-1);activeUnit=-1
                viewportW=-1;viewportH=-1
                return@forEachIndexed
            }
            val t=targets[idx]""")
once("    fun close(){","""    fun close(){
        mrtGroups.values.forEach{GLES30.glDeleteProgram(it.program)}
        mrtGroups.clear()
        if(mrtFbo[0]!=0)GLES30.glDeleteFramebuffers(1,mrtFbo,0)""")
p.write_text(s)
print("MRT: six four-output groups plus subpixel convolution and aggregation.")
