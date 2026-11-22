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
    private var referenceDiagnosticEnabled = false
    private var referenceHdrEnabled = false
    private var referenceVulkanEnabled = false
    private var vulkanHdrView: VulkanHdrBridgeView? = null
    private var scalerView: ReferenceScalerView? = null
    private var currentVideoFormat: Format? = null

    private fun resolvedScalerFormat(): Format? {
        // Media3 may deliver selected-track changes before/after decoded output.
        // ExoPlayer.videoFormat is the authoritative format currently being rendered.
        return player?.videoFormat ?: currentVideoFormat
    }

    private fun allowedForReferenceScaler(f: Format?): Boolean {
        if (f == null || f.width > 1920 || f.height > 1080 || f.width <= 0 || f.height <= 0) return false
        // Letterboxed/cropped movie files often store 1920x800, 1280x534 etc.
        // Classify by stored frame dimensions, not height alone.
        if (f.width < 960 && f.height < 540) return false
        if (f.sampleMimeType == MimeTypes.VIDEO_DOLBY_VISION) return false
        val transfer = f.colorInfo?.colorTransfer
        if (transfer == C.COLOR_TRANSFER_ST2084 || transfer == C.COLOR_TRANSFER_HLG) return false
        return true
    }

    private fun showRefliteScalerDialog() {
        val choices = arrayOf(
            "Original LitePlayer rendering",
            "ReferenceScaler GPU (normal)",
            "ReferenceScaler GPU DIAGNOSTIC (magenta corner)",
            "FSRCNNX SDR to HDR10 (experimental)",
            "Vulkan HDR10 output test (no video)",
            "FSRCNNX Vulkan SDR to HDR10 (live experimental)"
        )
        AlertDialog.Builder(this)
            .setTitle("Reflite video rendering")
            .setSingleChoiceItems(choices, if (!referenceScalerEnabled) 0 else if (referenceVulkanEnabled) 5 else if (referenceHdrEnabled) 3 else if (referenceDiagnosticEnabled) 2 else 1) { dialog, which ->
                if (which == 4) {
                    dialog.dismiss()
                    startActivity(android.content.Intent(this, VulkanHdrProbeActivity::class.java))
                    return@setSingleChoiceItems
                }
                val wantHdr = which == 3
                val wantVulkan = which == 5
                // EGL colours cannot be changed on a running GLSurfaceView.
                // Recreate only when toggling between HDR and SDR surfaces.
                if ((referenceHdrEnabled != wantHdr || referenceVulkanEnabled != wantVulkan) && scalerView != null) {
                    referenceScalerEnabled = false
                    applyRefliteScaler()
                }
                referenceHdrEnabled = wantHdr
                referenceVulkanEnabled = wantVulkan
                referenceScalerEnabled = which != 0
                referenceDiagnosticEnabled = which == 2
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
                val hdrView = vulkanHdrView
                vulkanHdrView = null
                (hdrView?.parent as? ViewGroup)?.removeView(hdrView)
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
                existing.setDiagnostic(referenceDiagnosticEnabled)
                return
            }
            val gpu = ReferenceScalerView(this, referenceHdrEnabled)
            gpu.onHdrUnavailable = { details ->
                val displayHdr = if (android.os.Build.VERSION.SDK_INT >= 24)
                    window.decorView.display?.hdrCapabilities?.supportedHdrTypes?.joinToString() ?: "unavailable"
                else "API too old"
                AlertDialog.Builder(this)
                    .setTitle("Reflite HDR output diagnostic")
                    .setMessage("HDR10 surface unavailable: continuing in SDR.\\n\\n" +
                        "Shield Android API: " + android.os.Build.VERSION.SDK_INT + "\\n" +
                        "Display HDR types: " + displayHdr + "\\n" +
                        details + "\\n\\n" +
                        "This tests the Shield graphics output. It does not alter FSRCNNX or the original HDR decoder.")
                    .setPositiveButton("OK", null)
                    .show()
            }
            scalerView = gpu
            gpu.setSourceSize(fmt.width, fmt.height)
            gpu.setDiagnostic(referenceDiagnosticEnabled)
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
            if (referenceVulkanEnabled) {
                val hdrView = VulkanHdrBridgeView(this)
                vulkanHdrView = hdrView
                gpu.attachVulkan(hdrView)
                hdrView.onFailure = { error ->
                    if (vulkanHdrView === hdrView) {
                        referenceVulkanEnabled = false
                        referenceScalerEnabled = false
                        applyRefliteScaler()
                        Toast.makeText(this, "Vulkan HDR unavailable: " + error, Toast.LENGTH_LONG).show()
                    }
                }
                parent.addView(hdrView, index + 2,
                    FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            }
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
# Restore saved bookmarks when an external launcher supplies a placeholder
# zero position. A deliberate "Play from beginning" still wins above.
replace_once(
    "return supplied?.coerceAtLeast(0L) ?: restoredPosition(u)",
    """return when {
            supplied != null && supplied > 0L -> supplied
            else -> restoredPosition(u)
        }"""
)
# Externally reported positions should match saved progress even if a caller
# returns after a decoder teardown resets ExoPlayer's currentPosition to zero.
replace_once(
    "val pos = player?.currentPosition ?: position",
    """val pos = (player?.currentPosition ?: position)
                .takeIf { it > 0L } ?: uri?.let { restoredPosition(it) } ?: 0L"""
)
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
