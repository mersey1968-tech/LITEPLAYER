"""Strip failed Vulkan experiment from the assembled Reflite GPU player.
Preserves the existing FSRCNNX neural scaler and Android package identity.
"""
from pathlib import Path

main = Path("proj/app/src/main/java/com/example/liteplayer/MainActivity.kt")
s = main.read_text()

def replace_once(old, new):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"MainActivity expected one replacement, got {count}: {old[:80]!r}")
    s = s.replace(old, new, 1)

replace_once(
    '    private var referenceVulkanEnabled = false\n    private var vulkanHdrView: VulkanHdrBridgeView? = null\n',
    ''
)
replace_once(
    '            "FSRCNNX Neural (SDR)",\n            "FSRCNNX Neural + HDR10 (Vulkan experimental)"',
    '            "FSRCNNX Neural (SDR)"'
)
replace_once(
    'if (!referenceScalerEnabled) 0 else if (referenceVulkanEnabled) 2 else 1',
    'if (referenceScalerEnabled) 1 else 0'
)
begin = s.index('                val wantHdr = false')
end = s.index('                referenceDiagnosticEnabled = false', begin)
s = s[:begin] + '''                referenceScalerEnabled = which == 1
                getSharedPreferences("reflite_video", MODE_PRIVATE).edit()
                    .putBoolean("neural_enabled", referenceScalerEnabled).apply()
''' + s[end:]
replace_once(
    '                val hdrView = vulkanHdrView\n                vulkanHdrView = null\n                (hdrView?.parent as? ViewGroup)?.removeView(hdrView)\n',
    ''
)
replace_once(
    '            val gpu = ReferenceScalerView(this, referenceHdrEnabled)',
    '            val gpu = ReferenceScalerView(this, false)'
)
begin = s.index('            if (referenceVulkanEnabled) {')
end = s.index('\n        }\n    }\n\n', begin)
s = s[:begin] + s[end:]
replace_once(
    '        val surface = (if (referenceVulkanEnabled) vulkanHdrView?.holder?.surface else scalerView?.holder?.surface) ?: (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface',
    '        val surface = scalerView?.holder?.surface ?: (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface'
)
# Read last selection when activity starts, and after tearing down the prior player.
replace_once(
    '        findViewById<Button>(R.id.refliteScalerButton).setOnClickListener { showRefliteScalerDialog() }',
    '''        referenceScalerEnabled = getSharedPreferences("reflite_video", MODE_PRIVATE)
            .getBoolean("neural_enabled", false)
        findViewById<Button>(R.id.refliteScalerButton).setOnClickListener { showRefliteScalerDialog() }'''
)
replace_once(
    '        referenceScalerEnabled = false\n        applyRefliteScaler()\n        currentVideoFormat = null',
    '''        referenceScalerEnabled = false
        applyRefliteScaler()
        referenceScalerEnabled = getSharedPreferences("reflite_video", MODE_PRIVATE)
            .getBoolean("neural_enabled", false)
        currentVideoFormat = null'''
)
# PlayerView's subtitles are in the app window. Ensure its normal UI remains above
# the GPU SurfaceView; a media overlay SurfaceView can hide every subtitle cue.
print("DEBUG MAIN declarations:", [(v, s.find(v)) for v in ("private lateinit var openButton", "private var smbAccess", "private lateinit var homePanel", "private lateinit var subtitleButton")])
print("DEBUG MAIN first 210 lines:", "\\n".join(s.splitlines()[:210]))
main.write_text(s)

renderer = Path("proj/app/src/main/java/com/example/liteplayer/ReferenceScalerView.kt")
r = renderer.read_text()
begin = r.index('    @Volatile private var vulkanBridge: VulkanHdrBridgeView?')
end = r.index('    fun setDiagnostic(enabled: Boolean)', begin)
r = r[:begin] + r[end:]
begin = r.index('            val bridge = vulkanBridge?.takeIf { it.isReady() }')
end = r.index('            if (sampleGpu) {', begin)
r = r[:begin] + '''            neuralPipeline?.render(texVideo, transform, workW, workH, outW, outH,
                diagnosticEnabled, false)
''' + r[end:]
begin = r.index('            if (sharedFbo != 0) vulkanBridge?.releaseSharedGL()')
end = r.index('\n        }', begin)
r = r[:begin] + r[end:]
r = r.replace('setZOrderMediaOverlay(true)', 'setZOrderMediaOverlay(false)')
assert 'VulkanHdrBridgeView' not in r and 'vulkanBridge' not in r
r = r.replace("                decoderFrameCount++\\n", "").replace("            glDrawCount++\\n", "")
renderer.write_text(r)
print("Reflite SDR-only neural renderer, subtitle layer and persistent selection staged.")
