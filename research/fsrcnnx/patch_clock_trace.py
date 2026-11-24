"""Read-only timing diagnostics; no changes to playback or shaders."""
from pathlib import Path
root=Path("proj/app/src/main/java/com/example/liteplayer")
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)
p=root/"MainActivity.kt"
s=p.read_text()
s=once(s,"    private val frameListener = VideoFrameMetadataListener { pts, _, _, _ ->","""    private var traceReleaseCount = 0
    private val frameListener = VideoFrameMetadataListener { pts, releaseNs, _, _ ->
        if (++traceReleaseCount % 8 == 0) {
            android.util.Log.i("RefliteClock", "release ptsUs=" + pts +
                " intendedNs=" + releaseNs + " callbackNs=" + System.nanoTime())
        }""")
p.write_text(s)
p=root/"ReferenceScalerView.kt"
s=p.read_text()
s=once(s,"    private var firstNeuralFrameReported = false","""    private var firstNeuralFrameReported = false
    private var traceFrameCount = 0""")
s=once(s,"            val newFrame = pending.getAndSet(false)","""            val newFrame = pending.getAndSet(false)
            val traceAcquireStartNs = System.nanoTime()""")
s=once(s,"            if (newFrame && !firstNeuralFrameReported) {","""            if (newFrame && srcH > 800 && ++traceFrameCount % 8 == 0) {
                Log.i("RefliteClock", "neural textureNs=" + surfaceTexture?.timestamp +
                    " acquireStartNs=" + traceAcquireStartNs +
                    " submitNs=" + System.nanoTime() + " scale=" + neuralScale)
            }
            if (newFrame && !firstNeuralFrameReported) {""")
s=once(s,"                val elapsedMs = (System.nanoTime() - start) / 1_000_000.0","""                val elapsedMs = (System.nanoTime() - start) / 1_000_000.0
                if (srcH > 800) Log.i("RefliteClock", "gpuDrainNs=" +
                    System.nanoTime() + " elapsedMs=" + elapsedMs)""")
p.write_text(s)
p=root/"audio/IecAudioOutput.kt"
s=p.read_text()
s=once(s,"\tprivate var underrunCount = 0","\tprivate var underrunCount = 0\n\tprivate var traceLastNs = 0L")
s=once(s,"\t\treturn if (playing) positionSmoother.smooth(rawPositionUs, System.nanoTime()) else rawPositionUs","""        val result = if (playing) positionSmoother.smooth(rawPositionUs, System.nanoTime()) else rawPositionUs
        if (nowNanos - traceLastNs >= 250_000_000L) {
            traceLastNs = nowNanos
            android.util.Log.i("RefliteClock", "iec nowNs=" + nowNanos +
                " headFrames=" + headFrames + " writtenFrames=" + writtenFrames +
                " selectedFrames=" + frames + " tsFrames=" + lastTimestampFrames +
                " tsNs=" + lastTimestampNanos + " rawUs=" + rawPositionUs +
                " smoothUs=" + result + " playing=" + playing + " underruns=" + underruns)
        }
        return result""")
s=once(s,"\toverride fun flush() {","\toverride fun flush() {\n        android.util.Log.i(\"RefliteClock\", \"iec flushNs=\" + System.nanoTime())")
p.write_text(s)
print("Clock trace staged; existing timing, audio and shaders unchanged.")
