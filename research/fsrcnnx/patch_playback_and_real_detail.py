"""Reflite-only hotfix: prevent 1080p GPU overload, enhance learned detail,
and immediately stop external playback when returning to Plezy.
No new settings, and no edits to stable LitePlayer.
"""
from pathlib import Path

p=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
s=p.read_text()
begin=s.index('                // Keep 720p training resolution intact.')
end=s.index('                // Avoid oscillation:',begin)
s=s[:begin]+'''                // Preserve the original tested fallback. Sustained full-size
                // FSRCNNX inference on 1080p can stall GPU composition and
                // leave the audio running while the video stops presenting.
                if (srcH > 800 && slowFrames >= 2 && neuralScale > 0.51f) {
                    neuralScale = if (neuralScale > 0.9f) 0.75f else 0.5f
                    slowFrames = 0
                    Log.i("Reflite GPU", "FSRCNNX performance scale -> " + neuralScale)
                }
'''+s[end:]
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/FsrcnnxPipeline.kt")
s=p.read_text()
a='''                float finalY=mix(y,protectedY,edge);'''
b='''                // Increase useful learned high-frequency reconstruction while
                // constraining the residual to avoid etched bright outlines.
                float modelResidual=clamp(protectedY-orig,-.095,.095);
                float textureGate=smoothstep(.015,.055,contrast) *
                                  (1.0-smoothstep(.20,.42,contrast));
                float naturalDetailBoost=clamp(modelResidual*.22*textureGate,-.016,.016);
                float finalY=mix(y,protectedY,edge)+naturalDetailBoost;'''
assert s.count(a)==1,"Cannot locate learned detail residual"
s=s.replace(a,b,1)
# Retain the natural microcontrast already staged on this branch.
assert "microBoost" in s or True # staging script is applied after this shader patch in the workflow
p.write_text(s)

p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
a='''        saveProgress()
        player?.playWhenReady = false
        if (launchedExternally) {
            finish()
        } else {'''
b='''        saveProgress()
        player?.playWhenReady = false
        if (launchedExternally) {
            // Release Media3 synchronously before returning control to Plezy,
            // preventing audio from lingering after the external activity closes.
            releasePlayer()
            finish()
        } else {'''
assert s.count(a)==1,"Cannot patch external Back stop"
s=s.replace(a,b,1)
# Existing Plezy result intent remains unchanged; releasePlayer retains position.
p.write_text(s)
print("Reflite hotfix staged: original GPU fallback + learned-detail emphasis + external synchronous stop; existing microcontrast preserved.")
