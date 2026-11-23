"""Render timed text and bitmap cues above the neural GLSurfaceView.
Only modifies the unpacked Reflite test copy; never touches LitePlayer.
"""
from pathlib import Path
p=Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s=p.read_text()
def once(old,new):
    global s
    n=s.count(old)
    if n!=1: raise RuntimeError(f"Expected exactly one match, got {n}: {old[:90]!r}")
    s=s.replace(old,new,1)

once("import androidx.media3.ui.PlayerView\n",
     "import androidx.media3.ui.PlayerView\nimport androidx.media3.ui.SubtitleView\n")
once("    private var scalerView: ReferenceScalerView? = null",
     """    private var scalerView: ReferenceScalerView? = null
    private var neuralSubtitleOverlay: SubtitleView? = null

    private fun styleNeuralSubtitleOverlay() {
        neuralSubtitleOverlay?.apply {
            setApplyEmbeddedStyles(true)
            setApplyEmbeddedFontSizes(false)
            setStyle(CaptionStyleCompat(Color.WHITE, Color.TRANSPARENT,
                Color.TRANSPARENT, CaptionStyleCompat.EDGE_TYPE_OUTLINE,
                Color.BLACK, null))
            setFractionalTextSize(subtitleSizes[selectedSubtitleIndex()])
        }
    }""")
once("            val cues = cueGroup.cues\n            if (cues.size < 2) return",
     """            val cues = cueGroup.cues
            neuralSubtitleOverlay?.setCues(cues)
            if (cues.size < 2) return""")
once("                        playerView.subtitleView?.setCues(toShow)",
     """                        playerView.subtitleView?.setCues(toShow)
                        neuralSubtitleOverlay?.setCues(toShow)""")
once("                val old = scalerView\n                scalerView = null",
     """                neuralSubtitleOverlay?.let { overlay ->
                    (overlay.parent as? ViewGroup)?.removeView(overlay)
                }
                neuralSubtitleOverlay = null
                val old = scalerView
                scalerView = null""")
once("""            parent.addView(gpu, index + 1,
                FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))""",
     """            parent.addView(gpu, index + 1,
                FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            // Unlike PlayerView subtitles, this dedicated Android view is above
            // the neural SurfaceView in the parent. It supports SRT and PGS cues.
            val subtitleOverlay = SubtitleView(this)
            subtitleOverlay.isClickable = false
            subtitleOverlay.isFocusable = false
            neuralSubtitleOverlay = subtitleOverlay
            parent.addView(subtitleOverlay, index + 2,
                FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            styleNeuralSubtitleOverlay()
            subtitleOverlay.setCues(activePlayer.currentCues.cues)""")
once("    private fun applySubtitleSize() {\n        val idx = selectedSubtitleIndex()",
     "    private fun applySubtitleSize() {\n        styleNeuralSubtitleOverlay()\n        val idx = selectedSubtitleIndex()")
p.write_text(s)
print("Reflite overlay: dedicated SubtitleView above neural GPU, live cues and persisted styling")
