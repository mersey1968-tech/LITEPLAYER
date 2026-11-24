"""Reflite 2.0: use a genuinely larger trained neural model at 540p/720p.
26-stage FSRCNNX 16-0-4-1, vs 14-stage 8-0-4-1 baseline at 1080p.
No changes to Android app/package name, launcher label, Plezy identity or UI.
Keep original neural processing as a fallback if stronger model fails to init.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''        check(sections.size==14){"Expected complete 14-stage FSRCNNX network"}'''
b='''        check(sections.size==14 || sections.size==26){"Unsupported FSRCNNX shader stage count: " + sections.size}'''
assert s.count(a)==1
s=s.replace(a,b,1)
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
a='''    private var neuralScale = 1.0f'''
b='''    private var neuralScale = 1.0f
    private var neural16Pipeline: FsrcnnxPipeline? = null
    private var neural16Unavailable = false
    private var lastModelName = ""'''
assert s.count(a)==1
s=s.replace(a,b,1)
a='''            neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false)'''
b='''            // 26-layer, 16-channel reconstruction for difficult TV
            // sources. Keep the lower-cost 8-channel net for 1080p films.
            val selected = if (srcH <= 800 && !neural16Unavailable) {
                if (neural16Pipeline == null) {
                    try {
                        val neuralModel16 = context.assets.open(
                            "reflite/FSRCNNX_x2_16-0-4-1.glsl")
                            .bufferedReader().use { it.readText() }
                        neural16Pipeline = FsrcnnxPipeline(neuralModel16)
                        Log.i("Reflite V2", "FSRCNNX 16-channel neural model initialized")
                    } catch (e: Throwable) {
                        neural16Unavailable = true
                        Log.e("Reflite V2",
                            "16-channel model unavailable: " + e.message +
                            "; using proven 8-channel fallback")
                    }
                }
                neural16Pipeline ?: neuralPipeline
            } else neuralPipeline
            val modelName = if (selected === neural16Pipeline && selected != null)
                "16-channel" else "8-channel"
            if (modelName != lastModelName) {
                lastModelName = modelName
                Log.i("Reflite V2", "Model=" + modelName +
                    " source=" + srcW + "x" + srcH +
                    " inference=" + workW + "x" + workH)
            }
            selected?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false)'''
assert s.count(a)==1, "SDR rendering call not found after safe Vulkan removal"
s=s.replace(a,b,1)
a='''            neuralPipeline?.close()
            neuralPipeline=null'''
b='''            neural16Pipeline?.close()
            neural16Pipeline=null
            neuralPipeline?.close()
            neuralPipeline=null'''
assert s.count(a)==1
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite V2 16-channel neural model selected automatically for <=800p; 1080p uses 8-channel; identity preserved")
