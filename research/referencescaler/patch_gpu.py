"""Overlay experimental ReferenceScaler onto the unpacked Reflite app copy.
Only executed by dedicated reflite-gpu.yml workflow on its test branch.
"""
from pathlib import Path

source = Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s = source.read_text()
def replace_once(old,new):
    global s
    n=s.count(old)
    if n != 1:
        raise RuntimeError("Expected one MainActivity match, got %s for %r" % (n,old[:90]))
    s=s.replace(old,new,1)

replace_once(
    "import android.view.SurfaceView\n",
    "import android.view.SurfaceView\nimport android.view.ViewGroup\nimport android.widget.FrameLayout\n"
)

replace_once(
    "    private lateinit var playerView: PlayerView\n",
    """    private lateinit var playerView: PlayerView

    // Reflite GPU rendering is opt-in and disabled by default.
    // Never change the established hardware-decoder SurfaceView path for HDR/4K.
    private var referenceScalerEnabled = false
    private var scalerView: ReferenceScalerView? = null
    private var currentVideoFormat: Format? = null

    private fun resolvedScalerFormat(): Format? {
        // Media3 may deliver selected-track changes before/after decoded output.
        // ExoPlayer.videoFormat is the authoritative format currently being rendered.
        return player?.videoFormat ?: currentVideoFormat
    }

    private fun allowedForReferenceScaler(f: Format?): Boolean {
        if (f == null || f.width < 1 || f.width > 1920 || f.height !in 540..1080) return false
        if (f.sampleMimeType == MimeTypes.VIDEO_DOLBY_VISION) return false
        val transfer = f.colorInfo?.colorTransfer
        if (transfer == C.COLOR_TRANSFER_ST2084 || transfer == C.COLOR_TRANSFER_HLG) return false
        return true
    }

    private fun showRefliteScalerDialog() {
        val choices = arrayOf("Original LitePlayer rendering", "ReferenceScaler GPU (experimental SDR 540p–1080p)")
        AlertDialog.Builder(this)
            .setTitle("Reflite video rendering")
            .setSingleChoiceItems(choices, if (referenceScalerEnabled) 1 else 0) { dialog, which ->
                referenceScalerEnabled = which == 1
                if (referenceScalerEnabled && !allowedForReferenceScaler(resolvedScalerFormat())) {
                    val fmt = resolvedScalerFormat()
                    val info = if (fmt == null) "video format not reported yet" else
                        "${fmt.width}×${fmt.height}, transfer=${fmt.colorInfo?.colorTransfer ?: -1}"
                    Toast.makeText(this, "Scaler cannot activate: $info", Toast.LENGTH_LONG).show()
                    referenceScalerEnabled = false
                }
                applyRefliteScaler()
                dialog.dismiss()
            }
            .setNegativeButton("Cancel", null).show()
    }

    private fun applyRefliteScaler() {
        val activePlayer = player
        if (!referenceScalerEnabled || !allowedForReferenceScaler(resolvedScalerFormat()) || activePlayer == null) {
            if (scalerView != null) {
                // Restore the established decoder target before releasing GPU resources.
                (playerView.videoSurfaceView as? SurfaceView)?.let { activePlayer?.setVideoSurfaceView(it) }
                val old = scalerView
                scalerView = null
                old?.onSurfaceReady = null
                (old?.parent as? ViewGroup)?.removeView(old)
                old?.onPause()
                old?.close()
            }
            return
        }
        resolvedScalerFormat()?.let { fmt ->
            val existing = scalerView
            if (existing != null) {
                existing.setSourceSize(fmt.width, fmt.height)
                return
            }
            val gpu = ReferenceScalerView(this)
            scalerView = gpu
            gpu.setSourceSize(fmt.width, fmt.height)
            gpu.onFailure = { failure ->
                if (scalerView === gpu) {
                    referenceScalerEnabled = false
                    applyRefliteScaler()
                    Toast.makeText(this, "GPU fallback: " + failure, Toast.LENGTH_LONG).show()
                }
            }
            gpu.onSurfaceReady = { surface ->
                if (referenceScalerEnabled && scalerView === gpu && player === activePlayer) {
                    activePlayer.setVideoSurface(surface)
                    applyFrameRate()
                }
            }
            // Add above video surface but below transport controls.
            val parent = playerView.parent as? FrameLayout
            if (parent == null) {
                referenceScalerEnabled = false
                scalerView = null
                Toast.makeText(this, "GPU overlay unavailable", Toast.LENGTH_LONG).show()
                return
            }
            val index = parent.indexOfChild(playerView)
            parent.addView(gpu, index + 1,
                FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
    }
"""
)
replace_once(
    "            applyHdr(format)\n            applyFrameRate()",
    "            currentVideoFormat = format\n            applyHdr(format)\n            applyRefliteScaler()\n            applyFrameRate()"
)
replace_once(
    "        seekSettingsButton.setOnClickListener { showSeekSettingsDialog() }",
    "        seekSettingsButton.setOnClickListener { showSeekSettingsDialog() }\n        findViewById<Button>(R.id.refliteScalerButton).setOnClickListener { showRefliteScalerDialog() }"
)
replace_once(
    "        player = null\n        playerView.player = null",
    "        referenceScalerEnabled = false\n        applyRefliteScaler()\n        currentVideoFormat = null\n        player = null\n        playerView.player = null"
)
replace_once(
    "        val surface = (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface",
    "        val surface = scalerView?.holder?.surface ?: (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface"
)
# Fix naming of controls: existing Seek settings button is reused for the renderer
# in experiment only. Ensure in the experimental APK it's labelled accurately.
source.write_text(s)
layout=Path("proj/app/src/main/res/layout/activity_main.xml")
x=layout.read_text()
needle='        <Button android:id="@+id/seekSettingsButton"'
if x.count(needle)!=1: raise RuntimeError("Could not locate seek control for safe scaler button insertion")
# Separate scaler toggle: do not steal the existing Skip settings button.
addition='''        <Button android:id="@+id/refliteScalerButton"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="Scaler" />
'''
# Insert just before the existing Skip button.
x=x.replace(needle,addition+needle,1)
layout.write_text(x)
gpu=Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
gpu.write_bytes(Path("research/referencescaler/ReferenceScalerView.kt").read_bytes())
print("Reflite GPU test integration overlaid; stable base unchanged")
