package com.example.liteplayer

import android.app.AlertDialog
import android.graphics.Color
import androidx.media3.ui.CaptionStyleCompat
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.media.AudioFormat
import android.media.AudioTrack
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.View
import android.view.KeyEvent
import android.widget.Button
import android.widget.TextView
import android.widget.ProgressBar
import android.widget.EditText
import android.text.InputType
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import android.widget.Toast
import android.provider.OpenableColumns
import org.json.JSONArray
import org.json.JSONObject
import android.widget.LinearLayout
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import java.security.MessageDigest
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.text.Cue
import androidx.media3.common.text.CueGroup
import androidx.media3.common.Format
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.Player
import androidx.media3.common.Tracks
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.audio.AudioTrackAudioOutputProvider
import com.example.liteplayer.audio.IecAudioOutputProvider
import androidx.media3.exoplayer.audio.AudioCapabilities
import androidx.media3.exoplayer.audio.AudioSink
import androidx.media3.exoplayer.audio.DefaultAudioSink
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.analytics.AnalyticsListener
import androidx.media3.exoplayer.video.VideoFrameMetadataListener
import androidx.media3.ui.PlayerView
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

@OptIn(UnstableApi::class)
class MainActivity : ComponentActivity() {

    private companion object {
        const val EXTERNAL_SUB_LABEL = "external-sub"
    }

    private lateinit var playerView: PlayerView
    private lateinit var openButton: Button
    private lateinit var infoText: TextView
    private lateinit var subtitleButton: Button
    private lateinit var seekIndicator: View
    private lateinit var homePanel: View
    private var smbAccess: SmbAccess? = null
    private lateinit var seekTimeLabel: TextView
    private lateinit var seekProgressBar: ProgressBar
    private val hideSeekIndicator = Runnable { seekIndicator.visibility = View.GONE }
    private var lastRemoteSeekAt = 0L
    private var lastRemoteSeekKey = KeyEvent.KEYCODE_UNKNOWN
    // Android TV remotes send repeated key-down events while a button is held.
    // Throttle seek requests to avoid flooding the decoder while scrubbing.
    private fun seekFromRemote(keyCode: Int, repeatCount: Int, seconds: Int) {
        val now = SystemClock.uptimeMillis()
        if (repeatCount == 0 || keyCode != lastRemoteSeekKey || now - lastRemoteSeekAt >= 180L) {
            seekRelative(seconds)
            lastRemoteSeekAt = now
            lastRemoteSeekKey = keyCode
        }
    }

    private fun installHoldToSeek(button: Button, seconds: () -> Int) {
        button.setOnKeyListener { _, code, event ->
            if (code != KeyEvent.KEYCODE_DPAD_CENTER &&
                code != KeyEvent.KEYCODE_ENTER &&
                code != KeyEvent.KEYCODE_NUMPAD_ENTER) return@setOnKeyListener false
            when (event.action) {
                KeyEvent.ACTION_DOWN -> {
                    seekFromRemote(code, event.repeatCount, seconds())
                    scheduleHide()
                    true
                }
                KeyEvent.ACTION_UP -> {
                    lastRemoteSeekKey = KeyEvent.KEYCODE_UNKNOWN
                    true // Avoid an additional Button click on release.
                }
                else -> false
            }
        }
    }
    private lateinit var revealControls: View
    private lateinit var controlPanel: LinearLayout
    private lateinit var playPauseButton: Button
    private lateinit var rewindButton: Button
    private lateinit var forwardButton: Button
    private lateinit var seekSettingsButton: Button
    private val progressHandler = Handler(Looper.getMainLooper())
    private val progressSaver = object : Runnable {
        override fun run() {
            saveProgress()
            progressHandler.postDelayed(this, 5000L)
        }
    }
    private val hideControls = Runnable { concealControls() }
    private var player: ExoPlayer? = null
    private var audioDecoderName = "not reported"
    private var audioInputFormat = "not selected"
    private val audioAnalytics = object : AnalyticsListener {
        override fun onAudioDecoderInitialized(
            eventTime: AnalyticsListener.EventTime,
            decoderName: String,
            initializedTimestampMs: Long,
            initializationDurationMs: Long
        ) {
            audioDecoderName = decoderName
        }
    }


    private var uri: Uri? = null
    private var position = 0L
    private var playWhenReady = true

    @Volatile private var videoFps = 0f
    private var lastFrameRateSurface: Surface? = null
    private var lastRequestedFrameRate = 0f
    @Volatile private var estimateDone = false
    private val frameTimes = ArrayList<Long>()

    private var activeIdentity: String? = null
    private var cachedProgressIdentity: String? = null
    private var cachedProgressKey: String? = null
    private var externalStartPosition = 0L
    private var lastKnownDuration = 0L
    private var launchedExternally = false
    private var ended = false

    private val picker = registerForActivityResult(ActivityResultContracts.OpenDocument()) {
        if (it == null) {
            openButton.visibility = View.VISIBLE
            return@registerForActivityResult
        }
        it.let { picked ->
            runCatching {
                contentResolver.takePersistableUriPermission(picked, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            releasePlayer()
            rememberRecent(picked)
            openStandalone(picked)

        }
    }

    // Fallback for streams that don't declare a frame rate: measure it from the first decoded frames.
    private val frameListener = VideoFrameMetadataListener { pts, _, _, _ ->
        if (!estimateDone && videoFps <= 0f) {
            var fps = 0f
            synchronized(frameTimes) {
                frameTimes.add(pts)
                if (frameTimes.size >= 48) {
                    val sorted = frameTimes.sorted()
                    val span = sorted.last() - sorted.first()
                    if (span > 0) fps = snapFps((sorted.size - 1) * 1_000_000f / span)
                    frameTimes.clear()
                    estimateDone = true
                }
            }
            val found = fps
            if (found > 0f) runOnUiThread { videoFps = found; applyFrameRate() }
        }
    }

    private val listener = object : Player.Listener {
        override fun onTracksChanged(tracks: Tracks) {
            val format = tracks.groups
                .firstOrNull { it.type == C.TRACK_TYPE_VIDEO && it.isSelected }
                ?.let { g -> (0 until g.length).firstOrNull { g.isTrackSelected(it) }?.let(g::getTrackFormat) }
            videoFps = format?.frameRate?.takeIf { it > 0f } ?: 0f
            estimateDone = videoFps > 0f
            synchronized(frameTimes) { frameTimes.clear() }
            applyHdr(format)
            applyFrameRate()
            val audio = tracks.groups.firstOrNull { it.type == C.TRACK_TYPE_AUDIO && it.isSelected }
                ?.let { group -> (0 until group.length).firstOrNull { group.isTrackSelected(it) }?.let(group::getTrackFormat) }
            audioInputFormat = audio?.let { "${it.sampleMimeType} codecs=${it.codecs ?: "?"} ${it.channelCount}ch" } ?: "none selected"
            selectBestAudioIfNeeded(tracks)
            selectSingleTextTrackIfNeeded(tracks)
            // Do not clear active cues here: the player will send the appropriate CueGroup.
            // SubtitleView may be refreshed when tracks change; restore the saved user size.
            restoreSubtitleStyleAfterRefresh()
        }

        override fun onCues(cueGroup: CueGroup) {
            // A stream may emit separate text cues at exactly the same screen
            // position; SubtitleView then draws two sentences over one another.
            // Keep the last cue at a colliding placement, but preserve true
            // multiline text inside one cue, cues positioned separately, and
            // image-based (PGS/VobSub) subtitles.
            val cues = cueGroup.cues
            if (cues.size < 2) return
            val toShow = ArrayList<Cue>(cues.size)
            var hasCollision = false
            for (cue in cues) {
                if (cue.text != null) {
                    val older = toShow.indexOfFirst { existing ->
                        existing.text != null &&
                            existing.line == cue.line &&
                            existing.lineType == cue.lineType &&
                            existing.lineAnchor == cue.lineAnchor &&
                            existing.position == cue.position &&
                            existing.positionAnchor == cue.positionAnchor
                    }
                    if (older >= 0) {
                        toShow.removeAt(older)
                        hasCollision = true
                    }
                }
                toShow.add(cue)
            }
            if (hasCollision) {
                val active = player
                // PlayerView receives the same event; apply the filtered set
                // after its regular subtitle update has completed.
                playerView.post {
                    if (active != null && active === player) {
                        playerView.subtitleView?.setCues(toShow)
                    }
                }
            }
        }

        override fun onRenderedFirstFrame() {
            // Start with a clean picture. A tap on the video reveals PlayerView controls.
            infoText.visibility = View.GONE
        }

        override fun onPlaybackStateChanged(state: Int) {
            if (state == Player.STATE_ENDED) {
                ended = true
                clearProgress()
                // When another app (e.g. Plezy) launched us, hand control back when the video finishes.
                if (launchedExternally) finish() else showHome()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (::playerView.isInitialized) restoreSubtitleStyleAfterRefresh()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        playerView = findViewById(R.id.playerView)
        // Do not automatically show controls when playback starts. A tap reveals them;
        // PlayerView hides them again after this timeout.
        playerView.useController = false
        playerView.controllerAutoShow = false
        playerView.controllerShowTimeoutMs = 3000
        revealControls = findViewById(R.id.revealControls)
        revealControls.setOnClickListener { revealControls() }
        openButton = findViewById(R.id.openButton)
        infoText = findViewById(R.id.infoText)
        subtitleButton = findViewById(R.id.subtitleButton)
        seekIndicator = findViewById(R.id.seekIndicator)
        seekTimeLabel = findViewById(R.id.seekTimeLabel)
        seekProgressBar = findViewById(R.id.seekProgressBar)
        homePanel = findViewById(R.id.homePanel)
        findViewById<Button>(R.id.browseFilesButton).setOnClickListener {
            picker.launch(arrayOf("video/*", "audio/*"))
        }
        findViewById<Button>(R.id.networkFilesButton).setOnClickListener { connectSmb() }
        findViewById<Button>(R.id.openUrlButton).setOnClickListener { promptForUrl() }
        findViewById<Button>(R.id.recentVideosButton).setOnClickListener { showRecents() }
        // Always reachable from the manually revealed transport panel.
        findViewById<Button>(R.id.audioSettingsButton).setOnClickListener { showAudioTracksDialog() }
        subtitleButton.setOnClickListener { showSubtitleDialog() }
        controlPanel = findViewById(R.id.controlPanel)
        playPauseButton = findViewById(R.id.playPauseButton)
        rewindButton = findViewById(R.id.rewindButton)
        forwardButton = findViewById(R.id.forwardButton)
        seekSettingsButton = findViewById(R.id.seekSettingsButton)
        playPauseButton.setOnClickListener {
            player?.let { it.playWhenReady = !it.playWhenReady }
            refreshPlayButton(); scheduleHide()
        }
        rewindButton.setOnClickListener { seekRelative(-seekBackSeconds); scheduleHide() }
        forwardButton.setOnClickListener { seekRelative(seekForwardSeconds); scheduleHide() }
        installHoldToSeek(rewindButton) { -seekBackSeconds }
        installHoldToSeek(forwardButton) { seekForwardSeconds }
        seekSettingsButton.setOnClickListener { showSeekSettingsDialog() }
        refreshSeekLabels()
        concealControls("startup")
        applySubtitleSize()
        openButton.setOnClickListener { picker.launch(arrayOf("video/*", "audio/*")) }

        (playerView.videoSurfaceView as? SurfaceView)?.holder?.addCallback(object : SurfaceHolder.Callback {
            override fun surfaceCreated(holder: SurfaceHolder) = applyFrameRate()
            override fun surfaceChanged(h: SurfaceHolder, f: Int, w: Int, ht: Int) {}
            override fun surfaceDestroyed(holder: SurfaceHolder) {
                lastFrameRateSurface = null
                lastRequestedFrameRate = 0f
            }
        })

        savedInstanceState?.let {
            uri = it.getString("uri")?.let(Uri::parse)
            position = it.getLong("pos")
            playWhenReady = it.getBoolean("play", true)
        }
        launchedExternally = intent?.action == Intent.ACTION_VIEW
        // Reconstruct the same identity after activity recreation so saves and restores
        // always address the same entry in SharedPreferences.
        if (uri != null) activeIdentity = identityFor(uri!!, intent)
        if (uri == null) {
            uri = intent?.takeIf { it.action == Intent.ACTION_VIEW }?.data
            uri?.let { activeIdentity = identityFor(it, intent); position = startingPosition(it, intent) }
        }
        applyImmersive(resources.configuration)
        // Standalone launches show the TV home. External players launch directly to video.
        if (uri == null) showHome() else homePanel.visibility = View.GONE

    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.data?.let { nextUri ->
            // Keep the video/audio pipeline alive for consecutive external playback requests.
            // Save the outgoing episode before changing its identity or URL.
            saveProgress()
            launchedExternally = intent.action == Intent.ACTION_VIEW
            homePanel.visibility = View.GONE
            concealControls("external playback")
            setIntent(intent)
            uri = nextUri
            activeIdentity = identityFor(nextUri, intent)
            position = startingPosition(nextUri, intent)
            ended = false
            playWhenReady = true
            manualAudioChoice = false
            lastAutoAudioKey = null
            val existing = player
            if (existing != null) {
                existing.setMediaItem(buildMediaItemWithSubtitles(nextUri))
                // Explicitly seek even when position is zero: a new episode must not
                // inherit the last video's playback position.
                existing.seekTo(position)
                existing.playWhenReady = true
                existing.prepare()
            } else {
                startPlayer()
            }
        }
    }

    override fun onStart() {
        super.onStart()
        startPlayer()
        progressHandler.removeCallbacks(progressSaver)
        progressHandler.postDelayed(progressSaver, 5000L)
    }
    override fun onPause() {
        saveProgress()
        super.onPause()
    }
    override fun onStop() {
        saveProgress()
        progressHandler.removeCallbacks(progressSaver)
        releasePlayer()
        super.onStop()
    }

    // Plex streaming URLs can carry changing tokens, while display titles can vary.
    // Prefer a stable Plex media/part identifier from the path or caller metadata.
    private fun identityFor(u: Uri, source: Intent?): String {
        val path = u.path.orEmpty()
        val plexId = Regex("/(?:library/)?(?:parts|metadata|media)/([0-9]+)").find(path)
            ?.groupValues?.get(1)
        if (plexId != null) return "plex:$plexId"
        val callerId = listOf("media_id", "ratingKey", "rating_key", "metadata_id", "key")
            .firstNotNullOfOrNull { key -> source?.getStringExtra(key)?.takeIf { it.isNotBlank() } }
        if (callerId != null) return "media:$callerId"
        // Ignore ephemeral URL query parameters (tokens, auth, timestamps).
        // Do not use title as the primary identity: titles can differ across launches.
        return "url:${u.scheme}://${u.authority}${u.path}"
    }

    private fun progressKey(u: Uri): String {
        val identity = activeIdentity ?: identityFor(u, null)
        if (cachedProgressIdentity == identity) cachedProgressKey?.let { return it }
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(identity.toByteArray(Charsets.UTF_8))
        val key = digest.joinToString("") { "%02x".format(it) }
        cachedProgressIdentity = identity
        cachedProgressKey = key
        return key
    }

    private fun startingPosition(u: Uri, source: Intent?): Long {
        // Plezy sends from_start=true for "Play from beginning" and omits
        // position/startfrom entirely. Do not load an old local bookmark then.
        // This flag is also used by VLC-style external-player intents.
        if (source?.getBooleanExtra("from_start", false) == true) {
            externalStartPosition = 0L
            return 0L
        }
        val supplied = listOf("position", "startfrom", "extra_position", "start_position", "startPosition", "resume_position", "resumePosition")
            .firstNotNullOfOrNull { key ->
                if (source?.hasExtra(key) == true) {
                    when (val v = source.extras?.get(key)) {
                        is Number -> v.toLong()
                        is String -> v.toLongOrNull()
                        else -> null
                    }
                } else null
            }
        externalStartPosition = supplied?.coerceAtLeast(0L) ?: 0L
        // Prefer the position explicitly supplied by Plezy. Fall back to
        // LitePlayer's local bookmark only when no start policy was supplied.
        return supplied?.coerceAtLeast(0L) ?: restoredPosition(u)
    }

    private fun restoredPosition(u: Uri): Long =
        getSharedPreferences("playback_progress", MODE_PRIVATE).getLong(progressKey(u), 0L)

    private fun clearProgress() {
        uri?.let { getSharedPreferences("playback_progress", MODE_PRIVATE).edit().remove(progressKey(it)).apply() }
    }

    private fun saveProgress() {
        val u = uri ?: return
        val p = player ?: return
        val duration = p.duration
        if (duration > 0 && duration != C.TIME_UNSET) lastKnownDuration = duration
        if (ended || p.playbackState == Player.STATE_ENDED) {
            clearProgress()
        } else if (p.currentPosition > 0L) {
            getSharedPreferences("playback_progress", MODE_PRIVATE).edit()
                .putLong(progressKey(u), p.currentPosition).apply()
        }
    }

    // Report back to the calling app (Plezy, MX Player-style and VLC-style results).
    override fun finish() {
        saveProgress()
        if (launchedExternally) {
            val pos = player?.currentPosition ?: position
            val dur = player?.duration?.takeIf { it > 0 && it != C.TIME_UNSET } ?: lastKnownDuration
            // Plezy's Android ExternalPlayerChannel recognizes playback_completion
            // only when the result action is the MX Player result action. A VLC
            // result action with end_by is treated as an ordinary stop instead.
            setResult(RESULT_OK, Intent("com.mxtech.intent.result.VIEW").apply {
                putExtra("end_by", if (ended) "playback_completion" else "user")
                putExtra("position", pos.coerceIn(0L, Int.MAX_VALUE.toLong()).toInt())
                putExtra("playback_position", pos)
                putExtra("duration", dur.coerceIn(0L, Int.MAX_VALUE.toLong()).toInt())
                // Preserve VLC-compatible extras for other external launchers.
                putExtra("extra_position", pos)
                putExtra("extra_duration", dur)
            })
        }
        super.finish()
    }

    override fun onSaveInstanceState(out: Bundle) {
        super.onSaveInstanceState(out)
        player?.let { position = it.currentPosition; playWhenReady = it.playWhenReady }
        out.putString("uri", uri?.toString())
        out.putLong("pos", position)
        out.putBoolean("play", playWhenReady)
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        applyImmersive(newConfig)
    }

    private fun startPlayer() {
        val u = uri ?: return
        if (player != null) return
        manualAudioChoice = false
        lastAutoAudioKey = null
        openButton.visibility = View.GONE
        homePanel.visibility = View.GONE

        val passthroughEnabled = getSharedPreferences("settings", MODE_PRIVATE).getBoolean("audioPassthrough", true)
        audioDecoderName = "not reported"
        audioInputFormat = "not selected"
        // For Auto passthrough, exclude the FFmpeg extension audio decoder.
        // The Android core audio renderer can send encoded audio to DefaultAudioSink
        // when the HDMI route advertises support; it may still decode to PCM otherwise.
        // The PCM mode retains its separately configured audio sink.
        val factory: DefaultRenderersFactory = if (passthroughEnabled) {
            // Shield TV / HDMI: Nova's "Force passthrough" works even when
            // Android's reported HDMI capabilities are incomplete. Tell the
            // Media3 audio sink which compressed formats to attempt directly.
            // Use the no-context builder deliberately: a context-backed sink
            // re-queries Android's capabilities and ignores this override.
            object : DefaultRenderersFactory(this@MainActivity) {
                override fun buildAudioSink(
                    context: android.content.Context,
                    enableFloatOutput: Boolean,
                    enableAudioOutputPlaybackParams: Boolean
                ): AudioSink {
                    val forced = AudioCapabilities(
                        intArrayOf(
                            C.ENCODING_PCM_16BIT,
                            C.ENCODING_AC3,
                            C.ENCODING_E_AC3,
                            C.ENCODING_E_AC3_JOC,
                            C.ENCODING_DTS,
                            C.ENCODING_DTS_HD,
                            C.ENCODING_DOLBY_TRUEHD
                        ),
                        8
                    )
                    return DefaultAudioSink.Builder(this@MainActivity)
                        .setAudioOutputProvider(
                            IecAudioOutputProvider(
                                AudioTrackAudioOutputProvider.Builder(this@MainActivity).build()
                            )
                        )
                        .setEnableFloatOutput(false)
                        .build()
                }
            }.apply {
                // Keep MediaCodec video rendering unchanged; don't let the
                // FFmpeg extension turn compressed audio into PCM first.
                setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_OFF)
                setEnableDecoderFallback(true)
                setEnableAudioFloatOutput(false)
            }
        } else {
            object : DefaultRenderersFactory(this@MainActivity) {
                override fun buildAudioSink(
                    context: android.content.Context,
                    enableFloatOutput: Boolean,
                    enableAudioOutputPlaybackParams: Boolean
                ): AudioSink {
                    return DefaultAudioSink.Builder()
                        .setAudioCapabilities(AudioCapabilities.DEFAULT_AUDIO_CAPABILITIES)
                        .build()
                }
            }.apply {
                setEnableDecoderFallback(true)
            }
        }

        val audioAttrs = AudioAttributes.Builder()
            .setUsage(C.USAGE_MEDIA)
            .setContentType(C.AUDIO_CONTENT_TYPE_MOVIE)
            .build()

        val loadControl = DefaultLoadControl.Builder()
            // Start local/LAN streams sooner without reducing the sustained buffer.
            .setBufferDurationsMs(30_000, 60_000, 1_500, 5_000)
            .build()
        val builder = ExoPlayer.Builder(this, factory)
            .setLoadControl(loadControl)
        if (u.scheme == "smb") {
            val access = smbAccess
            if (access == null) {
                Toast.makeText(this, "Reconnect to your SMB share", Toast.LENGTH_LONG).show()
                showHome()
                return
            }
            builder.setMediaSourceFactory(DefaultMediaSourceFactory(access.factory()))
        }
        player = builder
            .setAudioAttributes(audioAttrs, true)
            .build()
            .also {
                it.setVideoChangeFrameRateStrategy(C.VIDEO_CHANGE_FRAME_RATE_STRATEGY_OFF)
                it.setVideoFrameMetadataListener(frameListener)
                it.addListener(listener)
                it.addAnalyticsListener(audioAnalytics)
                playerView.player = it
                restoreSubtitleStyleAfterRefresh()
                it.setMediaItem(buildMediaItemWithSubtitles(u))
                if (position > 0L) it.seekTo(position)
                it.playWhenReady = playWhenReady
                it.prepare()
                // No playback-state callback is permitted to show controls.
            }
    }

    // Follow Just Player's MediaItem.SubtitleConfiguration approach for subtitles
    // explicitly supplied by the launching app. Embedded MKV subtitles are handled
    // automatically by Media3 and require no additional configuration.
    private fun buildMediaItemWithSubtitles(videoUri: Uri): MediaItem {
        // Subtitle files supplied by the launching app are ignored. Only subtitles built into
        // the video are used, so any double lines should stop if the extra file was the cause.
        return MediaItem.fromUri(videoUri)
    }

    private fun releasePlayer() {
        saveProgress()
        player?.let {
            position = it.currentPosition
            if (it.duration > 0 && it.duration != C.TIME_UNSET) lastKnownDuration = it.duration
            playWhenReady = it.playWhenReady
            it.release()
        }
        player = null
        playerView.player = null
        videoFps = 0f
        lastFrameRateSurface = null
        lastRequestedFrameRate = 0f
        window.attributes = window.attributes.apply { preferredDisplayModeId = 0 }
        applyHdr(null)
    }

    // ---- Info readout (shows for a few seconds so you can see what is happening) --------------

    private fun showInfo() {
        val hz = window.decorView.display?.refreshRate ?: 0f
        val src = if (videoFps > 0f) String.format(Locale.US, "%.3f fps", videoFps) else "unknown"
        val sb = StringBuilder(String.format(Locale.US, "Video: %s  |  Screen: %.1f Hz", src, hz))
        player?.audioFormat?.let { f ->
            val codec = f.sampleMimeType?.substringAfter('/') ?: "?"
            val ch = if (f.channelCount > 0) "  ${f.channelCount}ch" else ""
            sb.append("\nAudio: ").append(codec).append(ch)
        }
        sb.append("\nOutput can pass through: ").append(passthroughSupport())
        infoText.text = sb.toString()
        infoText.visibility = View.VISIBLE
        infoText.removeCallbacks(hideInfo)
        infoText.postDelayed(hideInfo, 8000)
    }

    // Which bitstream formats the connected audio output (HDMI, USB, ...) accepts untouched.
    private fun passthroughSupport(): String {
        if (Build.VERSION.SDK_INT < 29) return "unknown (needs Android 10+)"
        val attrs = android.media.AudioAttributes.Builder()
            .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
            .setContentType(android.media.AudioAttributes.CONTENT_TYPE_MOVIE)
            .build()
        val formats = listOf(
            "AC3" to AudioFormat.ENCODING_AC3,
            "E-AC3" to AudioFormat.ENCODING_E_AC3,
            "DTS" to AudioFormat.ENCODING_DTS,
            "DTS-HD" to AudioFormat.ENCODING_DTS_HD,
            "TrueHD" to AudioFormat.ENCODING_DOLBY_TRUEHD
        )
        val ok = formats.filter { (_, enc) ->
            val f = AudioFormat.Builder()
                .setEncoding(enc)
                .setSampleRate(48000)
                .setChannelMask(AudioFormat.CHANNEL_OUT_5POINT1)
                .build()
            AudioTrack.isDirectPlaybackSupported(f, attrs)
        }.map { it.first }
        return if (ok.isEmpty()) "none (audio is decoded)" else ok.joinToString(", ")
    }

    private var manualAudioChoice = false
    private var lastAutoAudioKey: String? = null

    private fun audioQuality(f: Format): Int {
        val mime = f.sampleMimeType.orEmpty().lowercase(Locale.US)
        val codec = f.codecs.orEmpty().lowercase(Locale.US)
        val tier = when {
            "dts.hd" in mime || "dts-hd" in codec -> 700
            "truehd" in mime || "mlp" in mime -> 700
            "flac" in mime || "alac" in mime || "raw" in mime -> 600
            "eac3" in mime || "e-ac3" in mime -> 400
            "dts" in mime -> 350
            "ac3" in mime -> 300
            else -> 100
        }
        val commentary = f.label.orEmpty().lowercase(Locale.US).let {
            "commentary" in it || "description" in it || "descriptive" in it
        }
        val languageBonus = if (f.language.equals("en", true) || f.language?.startsWith("en-", true) == true) 2000 else 0
        return languageBonus + tier + f.channelCount.coerceAtLeast(0).coerceAtMost(8) * 5 - if (commentary) 3000 else 0
    }

    // Only one subtitle track may be shown at a time. If the file has embedded subtitles and the
    // launching app also supplies a subtitle file, or a file has forced + full tracks, Media3 can
    // select several at once and they render on top of each other. Keep one: the launcher's file
    // first, then a normal (non-forced) track. Single choices made by the user are left alone.
    private fun selectSingleTextTrackIfNeeded(tracks: Tracks) {
        val p = player ?: return
        val selected = tracks.groups.flatMap { group ->
            if (group.type != C.TRACK_TYPE_TEXT) emptyList() else
                (0 until group.length).filter { group.isTrackSelected(it) }
                    .map { index -> Triple(group, index, group.getTrackFormat(index)) }
        }
        if (selected.size <= 1) return
        val best = selected.minByOrNull { (_, _, f) ->
            when {
                f.label == EXTERNAL_SUB_LABEL -> 0
                (f.selectionFlags and C.SELECTION_FLAG_FORCED) == 0 -> 1
                else -> 2
            }
        } ?: return
        p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
            .setOverrideForType(TrackSelectionOverride(best.first.mediaTrackGroup, listOf(best.second)))
            .build()
    }

    private fun selectBestAudioIfNeeded(tracks: Tracks) {
        if (manualAudioChoice) return
        val choices = tracks.groups.flatMap { group ->
            if (group.type != C.TRACK_TYPE_AUDIO) emptyList() else
                (0 until group.length).filter { group.isTrackSupported(it) }
                    .map { index -> Triple(group, index, audioQuality(group.getTrackFormat(index))) }
        }
        val best = choices.maxByOrNull { it.third } ?: return
        val key = "${best.first.mediaTrackGroup.id}:${best.second}"
        if (key == lastAutoAudioKey) return
        lastAutoAudioKey = key
        player?.trackSelectionParameters = player!!.trackSelectionParameters.buildUpon()
            .setOverrideForType(TrackSelectionOverride(best.first.mediaTrackGroup, listOf(best.second)))
            .build()
    }

    private fun showAudioTracksDialog() {
        val current = player ?: return
        val choices = current.currentTracks.groups.flatMap { group ->
            if (group.type != C.TRACK_TYPE_AUDIO) emptyList() else
                (0 until group.length).filter { group.isTrackSupported(it) }
                    .map { index -> Pair(group, index) }
        }
        if (choices.isEmpty()) {
            showAudioModeDialog()
            return
        }
        val labels = choices.map { (group, index) ->
            val f = group.getTrackFormat(index)
            "${f.language ?: "Unknown"} · ${f.label ?: f.sampleMimeType ?: "Audio"} · ${f.channelCount}ch"
        }.toTypedArray()
        val selected = choices.indexOfFirst { (group, index) -> group.isTrackSelected(index) }
        AlertDialog.Builder(this).setTitle("Audio tracks")
            .setSingleChoiceItems(labels, selected) { dialog, which ->
                val (group, index) = choices[which]
                manualAudioChoice = true
                current.trackSelectionParameters = current.trackSelectionParameters.buildUpon()
                    .setOverrideForType(TrackSelectionOverride(group.mediaTrackGroup, listOf(index)))
                    .build()
                dialog.dismiss()
                scheduleHide()
            }
            .setNeutralButton("Auto best") { _, _ ->
                manualAudioChoice = false
                lastAutoAudioKey = null
                current.trackSelectionParameters = current.trackSelectionParameters.buildUpon()
                    .clearOverridesOfType(C.TRACK_TYPE_AUDIO).build()
                selectBestAudioIfNeeded(current.currentTracks)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showAudioModeDialog() {
        val prefs = getSharedPreferences("settings", MODE_PRIVATE)
        val current = if (prefs.getBoolean("audioPassthrough", true)) 0 else 1
        AlertDialog.Builder(this)
            .setTitle("Audio output")
            .setSingleChoiceItems(arrayOf("Auto passthrough (when supported)", "Decode to PCM (no passthrough)"), current) { dialog, which ->
                val enabled = which == 0
                prefs.edit().putBoolean("audioPassthrough", enabled).apply()
                dialog.dismiss()
                // Recreate the player so the selected output mode takes effect immediately.
                player?.let {
                    position = it.currentPosition
                    playWhenReady = it.playWhenReady
                    releasePlayer()
                    startPlayer()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // The controller is not attached until the user explicitly requests it. This avoids
    // the initial PlayerView controller flash during prepare/buffering/track changes.
    private fun concealControls(reason: String = "timeout/back") {
        playerView.removeCallbacks(hideControls)
        playerView.useController = false
        controlPanel.visibility = View.GONE
        subtitleButton.visibility = View.GONE
        revealControls.visibility = View.VISIBLE
    }

    private fun revealControls() {
        revealControls.visibility = View.GONE
        controlPanel.visibility = View.VISIBLE
        refreshPlayButton()
        subtitleButton.visibility = View.VISIBLE
        // TV D-pad: OK must focus Play/Pause, never the rewind button.
        playPauseButton.isFocusableInTouchMode = true
        playPauseButton.requestFocus()
        scheduleHide()
    }

    private fun scheduleHide() {
        playerView.removeCallbacks(hideControls)
        playerView.postDelayed(hideControls, 3000L)
    }

    private fun refreshPlayButton() {
        playPauseButton.text = if (player?.playWhenReady == true) "Pause" else "Play"
    }

    private fun formatSeekTime(ms: Long): String {
        val total = ms.coerceAtLeast(0L) / 1000L
        val h = total / 3600L
        val m = (total / 60L) % 60L
        val sec = total % 60L
        return if (h > 0) String.format(Locale.US, "%d:%02d:%02d", h, m, sec)
            else String.format(Locale.US, "%02d:%02d", m, sec)
    }

    // Seek feedback is independent of the hidden player controls. Repeated
    // remote presses refresh this lightweight overlay without displaying menus.
    private fun seekRelative(seconds: Int) {
        val active = player ?: return
        val duration = active.duration.takeIf { it > 0 && it != C.TIME_UNSET }
        val target = (active.currentPosition + seconds * 1000L)
            .coerceAtLeast(0L)
            .let { if (duration != null) it.coerceAtMost(duration) else it }
        active.seekTo(target)
        seekTimeLabel.text = if (duration != null)
            "${formatSeekTime(target)} / ${formatSeekTime(duration)}"
        else formatSeekTime(target)
        seekProgressBar.progress = if (duration != null)
            ((target.toDouble() / duration.toDouble()) * seekProgressBar.max)
                .roundToInt().coerceIn(0, seekProgressBar.max)
        else 0
        seekIndicator.visibility = View.VISIBLE
        seekIndicator.removeCallbacks(hideSeekIndicator)
        seekIndicator.postDelayed(hideSeekIndicator, 1800L)
    }

    // Return to Plezy on external playback; return to LitePlayer home for local playback.
    private fun exitToCaller() {
        saveProgress()
        player?.playWhenReady = false
        if (launchedExternally) finish() else showHome()
    }

    // Catch remote Back before the player view or its controls can consume it.
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_BACK) {
            if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) exitToCaller()
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    @Deprecated("Handled explicitly for Android TV remote Back")
    override fun onBackPressed() {
        exitToCaller()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        // With the overlay hidden, LEFT/RIGHT seek without showing controls.
        // When controls are open, retain standard D-pad navigation and focus.
        if (controlPanel.visibility != View.VISIBLE) {
            when (keyCode) {
                KeyEvent.KEYCODE_DPAD_LEFT -> {
                    seekFromRemote(keyCode, event.repeatCount, -seekBackSeconds)
                    return true
                }
                KeyEvent.KEYCODE_DPAD_RIGHT -> {
                    seekFromRemote(keyCode, event.repeatCount, seekForwardSeconds)
                    return true
                }
            }
        }
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            exitToCaller()
            return true
        }

        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (controlPanel.visibility != View.VISIBLE) {
                revealControls()
                return true
            }
        }
        if (controlPanel.visibility == View.VISIBLE) scheduleHide()
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT || keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
            lastRemoteSeekKey = KeyEvent.KEYCODE_UNKNOWN
            if (controlPanel.visibility != View.VISIBLE) return true
        }
        return super.onKeyUp(keyCode, event)
    }

    private fun showHome() {
        if (player != null) releasePlayer()
        uri = null
        activeIdentity = null
        cachedProgressIdentity = null
        cachedProgressKey = null
        position = 0L
        ended = false
        seekIndicator.removeCallbacks(hideSeekIndicator)
        seekIndicator.visibility = View.GONE
        playerView.removeCallbacks(hideControls)
        controlPanel.visibility = View.GONE
        subtitleButton.visibility = View.GONE
        revealControls.visibility = View.GONE
        openButton.visibility = View.GONE
        homePanel.visibility = View.VISIBLE
        findViewById<Button>(R.id.browseFilesButton).requestFocus()
    }

    private fun openStandalone(next: Uri) {
        launchedExternally = false
        homePanel.visibility = View.GONE
        concealControls("standalone playback")
        uri = next
        activeIdentity = identityFor(next, null)
        position = restoredPosition(next)
        playWhenReady = true
        ended = false
        startPlayer()
    }

    private fun promptForUrl() {
        val input = EditText(this).apply {
            hint = "https://example.com/movie.mkv"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine(true)
        }
        AlertDialog.Builder(this).setTitle("Open stream URL")
            .setView(input)
            .setPositiveButton("Play") { _, _ ->
                val value = input.text.toString().trim()
                val parsed = Uri.parse(value)
                if ((parsed.scheme == "https" || parsed.scheme == "http") && !parsed.host.isNullOrBlank()) {
                    openStandalone(parsed)
                } else Toast.makeText(this, "Enter a valid http:// or https:// URL", Toast.LENGTH_LONG).show()
            }
            .setNegativeButton("Cancel", null).show()
    }

    // Record only files explicitly selected by the user. Never retain Plezy tokens.
    private fun rememberRecent(chosen: Uri) {
        val prefs = getSharedPreferences("recent_files", MODE_PRIVATE)
        val current = runCatching { JSONArray(prefs.getString("items", "[]")) }.getOrDefault(JSONArray())
        val next = JSONArray()
        val name = runCatching {
            contentResolver.query(chosen, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
        }.getOrNull() ?: chosen.lastPathSegment ?: "Video"
        next.put(JSONObject().put("uri", chosen.toString()).put("name", name))
        for (i in 0 until current.length()) {
            val entry = current.optJSONObject(i) ?: continue
            if (entry.optString("uri") != chosen.toString() && next.length() < 8) next.put(entry)
        }
        prefs.edit().putString("items", next.toString()).apply()
    }

    private fun showRecents() {
        val saved = getSharedPreferences("recent_files", MODE_PRIVATE).getString("items", "[]")
        val items = runCatching { JSONArray(saved) }.getOrDefault(JSONArray())
        if (items.length() == 0) {
            Toast.makeText(this, "No recent files yet", Toast.LENGTH_SHORT).show()
            return
        }
        val labels = Array(items.length()) { items.optJSONObject(it)?.optString("name").orEmpty() }
        AlertDialog.Builder(this).setTitle("Recent files")
            .setItems(labels) { _, index ->
                val path = items.optJSONObject(index)?.optString("uri").orEmpty()
                if (path.isNotBlank()) openStandalone(Uri.parse(path))
            }.setNegativeButton("Cancel", null).show()
    }

    private fun connectSmb() {
        val prefs = getSharedPreferences("smb_connection", MODE_PRIVATE)
        val fields = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 12, 36, 12)
        }
        val server = EditText(this).apply {
            hint = "smb://192.168.1.10/Movies/"
            setSingleLine(true)
            setText(prefs.getString("share", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        val username = EditText(this).apply {
            hint = "Username (leave blank for guest)"
            setSingleLine(true)
            setText(prefs.getString("user", ""))
        }
        val password = EditText(this).apply {
            hint = "Password (not saved)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setSingleLine(true)
        }
        fields.addView(server)
        fields.addView(username)
        fields.addView(password)
        AlertDialog.Builder(this)
            .setTitle("Connect to SMB / NAS")
            .setView(fields)
            .setPositiveButton("Connect") { _, _ ->
                val folder = server.text.toString().trim().replace('\\', '/')
                    .let { if (it.endsWith("/")) it else "$" + "{it}/" }
                val parsed = Uri.parse(folder)
                if (parsed.scheme != "smb" || parsed.host.isNullOrBlank() ||
                    parsed.pathSegments.isEmpty() || parsed.userInfo != null) {
                    Toast.makeText(this, "Use smb://server/share/", Toast.LENGTH_LONG).show()
                } else {
                    val user = username.text.toString().trim()
                    // Save only the server/share path and username, never the password.
                    prefs.edit().putString("share", folder).putString("user", user).apply()
                    smbAccess = SmbAccess(user, password.text.toString())
                    browseSmb(folder)
                }
            }.setNegativeButton("Cancel", null).show()
    }

    private fun browseSmb(folder: String) {
        val access = smbAccess ?: return connectSmb()
        val pending = AlertDialog.Builder(this).setMessage("Opening network folder…")
            .setCancelable(false).create()
        pending.show()
        Thread {
            val result = runCatching { access.entries(folder) }
            runOnUiThread {
                if (isFinishing || isDestroyed) { pending.dismiss(); return@runOnUiThread }
                pending.dismiss()
                result.onFailure { error ->
                    AlertDialog.Builder(this).setTitle("Network error")
                        .setMessage(error.message ?: "Unable to open SMB share")
                        .setPositiveButton("Retry") { _, _ -> browseSmb(folder) }
                        .setNegativeButton("Cancel", null).show()
                }.onSuccess { entries ->
                    val showUp = folder.substringAfter("smb://").trimEnd('/').contains('/')
                    val filtered = entries.filter {
                        it.second || it.first.substringAfterLast('.').lowercase() in
                            setOf("mkv", "mp4", "avi", "mov", "m4v", "ts", "m2ts", "webm", "mpg", "mpeg")
                    }
                    val labels = (if (showUp) listOf("..  Up one folder") else emptyList()) +
                        filtered.map { (name, dir) ->
                            (if (dir) "📁  " else "▶  ") + name.trimEnd('/')
                        }
                    AlertDialog.Builder(this).setTitle(folder)
                        .setItems(labels.toTypedArray()) { _, which ->
                            if (showUp && which == 0) {
                                val up = folder.trimEnd('/').substringBeforeLast('/') + "/"
                                browseSmb(up)
                            } else {
                                val (name, isDir) = filtered[which - (if (showUp) 1 else 0)]
                                val url = folder + Uri.encode(name.trimEnd('/')) + if (isDir) "/" else ""
                                if (isDir) browseSmb(url)
                                else {
                                    releasePlayer()
                                    openStandalone(Uri.parse(url))
                                }
                            }
                        }
                        .setNegativeButton("Home", null).show()
                }
            }
        }.start()
    }

    // ---- Subtitle size -----------------------------------------------------------------------

    // Denser spacing between Small and Medium; stored separately so older indices
    // never silently select a different size after an app upgrade.
    private val subtitleSizes = floatArrayOf(0.012f, 0.017f, 0.022f, 0.028f, 0.034f, 0.040f, 0.046f, 0.0533f, 0.070f, 0.090f)
    private val subtitleNames = arrayOf("Tiny", "Very small", "Small", "Small +", "Medium -", "Medium", "Medium +", "Large", "Extra large", "Huge")
    private fun selectedSubtitleIndex(): Int {
        val prefs = getSharedPreferences("settings", MODE_PRIVATE)
        if (prefs.contains("subSizeV2")) return prefs.getInt("subSizeV2", 4).coerceIn(subtitleSizes.indices)
        if (!prefs.contains("subSize")) return 4 // Medium - is the first-run default.
        val old = prefs.getInt("subSize", 2).coerceIn(0, 6)
        return intArrayOf(0, 1, 2, 7, 8, 9, 9)[old]
    }

    private val seekChoices = intArrayOf(5, 10, 15, 20, 30, 60, 120)
    private val seekBackSeconds: Int get() = getSharedPreferences("settings", MODE_PRIVATE).getInt("seekBack", 10)
    private val seekForwardSeconds: Int get() = getSharedPreferences("settings", MODE_PRIVATE).getInt("seekForward", 30)

    private fun refreshSeekLabels() {
        rewindButton.text = "-${seekBackSeconds}s"
        forwardButton.text = "+${seekForwardSeconds}s"
    }

    private fun showSeekSettingsDialog() {
        val items = arrayOf("Rewind: ${seekBackSeconds}s", "Forward: ${seekForwardSeconds}s")
        AlertDialog.Builder(this).setTitle("Skip intervals")
            .setItems(items) { _, which ->
                val key = if (which == 0) "seekBack" else "seekForward"
                val current = if (which == 0) seekBackSeconds else seekForwardSeconds
                val labels = seekChoices.map { "${it} seconds" }.toTypedArray()
                AlertDialog.Builder(this)
                    .setTitle(if (which == 0) "Rewind interval" else "Forward interval")
                    .setSingleChoiceItems(labels, seekChoices.indexOf(current)) { dialog, index ->
                        getSharedPreferences("settings", MODE_PRIVATE).edit()
                            .putInt(key, seekChoices[index]).apply()
                        refreshSeekLabels()
                        dialog.dismiss()
                        scheduleHide()
                    }
                    .setNegativeButton("Cancel", null)
                    .show()
            }.setNegativeButton("Cancel", null).show()
    }

    // Media3 may recreate/refresh SubtitleView styling after a player attach or cue update.
    // Reapply the persisted preference on the next frame and after the refresh settles.
    private fun restoreSubtitleStyleAfterRefresh() {
        applySubtitleSize()
        playerView.post { applySubtitleSize() }
        playerView.postDelayed({ applySubtitleSize() }, 250L)
        playerView.postDelayed({ applySubtitleSize() }, 1000L)
    }

    private fun applySubtitleSize() {
        val idx = selectedSubtitleIndex()
        playerView.subtitleView?.apply {
            // Preserve SRT text styling, including italics and Unicode glyphs.
            // Suppress the opaque caption background while retaining a readable outline.
            setApplyEmbeddedStyles(true)
            setApplyEmbeddedFontSizes(false)
            setStyle(CaptionStyleCompat(
                Color.WHITE,
                Color.TRANSPARENT,
                Color.TRANSPARENT,
                CaptionStyleCompat.EDGE_TYPE_OUTLINE,
                Color.BLACK,
                null
            ))
            setFractionalTextSize(subtitleSizes[idx])
        }
    }

    private fun showSubtitleDialog() {
        val prefs = getSharedPreferences("settings", MODE_PRIVATE)
        AlertDialog.Builder(this)
            .setTitle("Subtitle size")
            .setSingleChoiceItems(subtitleNames, selectedSubtitleIndex()) { d, which ->
                prefs.edit().putInt("subSizeV2", which).commit()
                restoreSubtitleStyleAfterRefresh()
                d.dismiss()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }


    private val hideInfo = Runnable { infoText.visibility = View.GONE }

    // ---- HDR -------------------------------------------------------------------------------

    private fun applyHdr(format: Format?) {
        if (Build.VERSION.SDK_INT < 26) return
        val transfer = format?.colorInfo?.colorTransfer
        val hdr = transfer == C.COLOR_TRANSFER_ST2084 ||
            transfer == C.COLOR_TRANSFER_HLG ||
            format?.sampleMimeType == MimeTypes.VIDEO_DOLBY_VISION
        window.colorMode = if (hdr) ActivityInfo.COLOR_MODE_HDR else ActivityInfo.COLOR_MODE_DEFAULT
    }

    // ---- Frame-rate matching -----------------------------------------------------------------

    private fun snapFps(raw: Float): Float {
        val common = floatArrayOf(23.976f, 24f, 25f, 29.97f, 30f, 47.952f, 48f, 50f, 59.94f, 60f)
        val best = common.minByOrNull { abs(it - raw) / it } ?: return raw
        return if (abs(best - raw) / best < 0.02f) best else raw
    }

    private fun applyFrameRate() {
        val fps = videoFps
        if (fps <= 0f) return
        val surface = (playerView.videoSurfaceView as? SurfaceView)?.holder?.surface
        if (surface == null || !surface.isValid) return
        // Track requests per Surface: track callbacks can repeat the same FPS.
        // Never suppress the first request on a newly created Surface.
        if (surface === lastFrameRateSurface && abs(fps - lastRequestedFrameRate) < 0.001f) return
        lastFrameRateSurface = surface
        lastRequestedFrameRate = fps
        when {
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

    private fun pickDisplayMode(fps: Float) {
        val display = window.decorView.display ?: return
        val cur = display.mode
        val best = display.supportedModes
            .filter { it.physicalWidth == cur.physicalWidth && it.physicalHeight == cur.physicalHeight }
            .minByOrNull { m ->
                val k = (m.refreshRate / fps).roundToInt().coerceAtLeast(1)
                abs(m.refreshRate - fps * k) * 100f + k
            } ?: return
        window.attributes = window.attributes.apply { preferredDisplayModeId = best.modeId }
    }

    private fun applyImmersive(cfg: Configuration) {
        val c = WindowInsetsControllerCompat(window, window.decorView)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        if (cfg.orientation == Configuration.ORIENTATION_LANDSCAPE) {
            c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            c.hide(WindowInsetsCompat.Type.systemBars())
        } else c.show(WindowInsetsCompat.Type.systemBars())
    }
}
