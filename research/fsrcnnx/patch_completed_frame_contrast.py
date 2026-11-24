"""Wait for first neural GPU completion before restoring playback.
Keep existing shader model and adaptive resolution behavior.
"""
from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=once(s,"""                firstNeuralFrameReported = true
                // Submitted on the GL thread; callback is not a display-present guarantee.
                post { onFirstNeuralFrame?.invoke() }""","""                // One startup-only GPU drain, not a per-frame stall.
                // Completion is not proof of physical display scanout.
                if (srcH > 800) GLES30.glFinish()
                firstNeuralFrameReported = true
                post { onFirstNeuralFrame?.invoke() }""")
p.write_text(s)
p=root/"MainActivity.kt"
s=p.read_text()
s=once(s,"""                            .postDelayed({ resume() }, 800L)""","""                            .postDelayed({
                                if (waitingForNeuralFrame && player === activePlayer &&
                                    scalerView === gpu && referenceScalerEnabled && !isFinishing) {
                                    // If the paused decoder cannot deliver a frame,
                                    // restore direct playback instead of resuming
                                    // audio against an unready neural renderer.
                                    waitingForNeuralFrame = false
                                    referenceScalerEnabled = false
                                    applyRefliteScaler()
                                    activePlayer.playWhenReady = true
                                    Toast.makeText(this, "Neural startup timed out; original playback restored",
                                        Toast.LENGTH_SHORT).show()
                                }
                            }, 5000L)""")
p.write_text(s)
p=root/"FsrcnnxPipeline.kt"
s=p.read_text()
s=once(s,"""                reconstructed*=1.0-shadowDepth*shadowRange;
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);""","""                reconstructed*=1.0-shadowDepth*shadowRange;
                // Gentle SDR midtone S curve, zero extra texture reads.
                // Endpoint and midpoint preservation; chroma-neutral delta
                // bounded by available RGB headroom to avoid extra clipping.
                if (uHdr < 0.5) {
                    float tone=dot(reconstructed,vec3(.2126,.7152,.0722));
                    float delta=.12*tone*(1.0-tone)*(2.0*tone-1.0);
                    float lo=min(reconstructed.r,min(reconstructed.g,reconstructed.b));
                    float hi=max(reconstructed.r,max(reconstructed.g,reconstructed.b));
                    reconstructed+=vec3(clamp(delta,-lo,1.0-hi));
                }
                outColor=vec4(uHdr>0.5?sdrToHdr10(reconstructed):reconstructed,1.);""")
p.write_text(s)
print("Completed-frame startup gate and modest SDR contrast curve staged.")
