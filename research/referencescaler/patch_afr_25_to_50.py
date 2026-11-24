"""Keep Reflite Natural Depth video quality intact; fix 25 fps display AFR.

Android 12+ Surface.setFrameRate(fps) alone lets system choose 30 Hz in some
overlay configurations. Explicitly prefer 50 Hz for 25 fps video, including
Android 12+ devices, while preserving true video fps for the decoder and audio.
Only modifies MainActivity's frame-rate mode selection function.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
a='''        when {
            Build.VERSION.SDK_INT >= 31 -> surface.setFrameRate(
                fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE, Surface.CHANGE_FRAME_RATE_ALWAYS
            )
            Build.VERSION.SDK_INT >= 30 -> {
                surface.setFrameRate(fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE)
                pickDisplayMode(fps)
            }
            else -> pickDisplayMode(fps)
        }
    }

    private fun pickDisplayMode(fps: Float) {'''
b='''        when {
            Build.VERSION.SDK_INT >= 31 -> surface.setFrameRate(
                fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE, Surface.CHANGE_FRAME_RATE_ALWAYS
            )
            Build.VERSION.SDK_INT >= 30 -> {
                surface.setFrameRate(fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE)
                pickDisplayMode(fps)
            }
            else -> pickDisplayMode(fps)
        }
        // Android 12+ does not always select a clean multiple for an external
        // GPU overlay. Keep the actual source at 25 fps, but prefer a display
        // refresh of 50 Hz (2:2 repeat) instead of 30 Hz (uneven cadence).
        // All other source rates keep the proven existing Android matching.
        if (Build.VERSION.SDK_INT >= 31 && kotlin.math.abs(fps-25f) < 0.25f) {
            pickDisplayMode(fps)
        }
    }

    private fun pickDisplayMode(fps: Float) {'''
assert s.count(a)==1, "applyFrameRate anchor changed"
s=s.replace(a,b,1)
a='''        val best = display.supportedModes
            .filter { it.physicalWidth == cur.physicalWidth && it.physicalHeight == cur.physicalHeight }
            .minByOrNull { m ->
                val k = (m.refreshRate / fps).roundToInt().coerceAtLeast(1)
                abs(m.refreshRate - fps * k) * 100f + k
            } ?: return
        window.attributes = window.attributes.apply { preferredDisplayModeId = best.modeId }'''
b='''        val modes = display.supportedModes
            .filter { it.physicalWidth == cur.physicalWidth && it.physicalHeight == cur.physicalHeight }
        // Some 4K displays expose multiple 25 fps-compatible modes. Select
        // an actual 50 Hz mode first, not 25/30/other-mode heuristics.
        val best = if (kotlin.math.abs(fps-25f) < 0.25f) {
            modes.filter { kotlin.math.abs(it.refreshRate-50f) < 0.25f }
                .minByOrNull { kotlin.math.abs(it.refreshRate-50f) }
                ?: modes.minByOrNull { m ->
                    val k = (m.refreshRate / fps).roundToInt().coerceAtLeast(1)
                    kotlin.math.abs(m.refreshRate - fps * k) * 100f + k
                }
        } else {
            modes.minByOrNull { m ->
                val k = (m.refreshRate / fps).roundToInt().coerceAtLeast(1)
                kotlin.math.abs(m.refreshRate - fps * k) * 100f + k
            }
        } ?: return
        window.attributes = window.attributes.apply { preferredDisplayModeId = best.modeId }
        android.util.Log.i("Reflite AFR",
            "source=" + fps + "fps preferred=" + best.refreshRate +
            "Hz modeId=" + best.modeId + " current=" + cur.refreshRate + "Hz")'''
assert s.count(a)==1, "pickDisplayMode anchor changed"
s=s.replace(a,b,1)
p.write_text(s)
print("Reflite AFR 25->50 Hz request on Android 12+; neural render, sound, subs, and Plezy untouched.")
