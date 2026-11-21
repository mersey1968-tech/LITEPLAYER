package com.example.liteplayer.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.Build
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.annotation.RequiresApi
import androidx.media3.common.C
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.audio.AudioOutput
import androidx.media3.exoplayer.audio.AudioOutputProvider
import androidx.media3.exoplayer.audio.ForwardingAudioOutputProvider
import androidx.media3.extractor.Ac3Util
import androidx.media3.extractor.DtsUtil
import android.util.Log

/**
 * Plays DTS, DTS-HD and TrueHD as IEC 61937 bursts packed by the app ([IecAudioOutput]) and forwards everything else
 * to [delegate]. This sends the lossless formats to the receiver unchanged on devices whose audio HAL does not pass
 * them through itself.
 *
 * Media3 releases the audio output on every flush (see `DefaultAudioSink.flush`), and a new IEC track makes the
 * receiver lock onto the stream again, which mutes the first second after every seek. The provider therefore keeps a
 * released track for a few seconds and hands it to the next output.
 */
@OptIn(UnstableApi::class)
class IecAudioOutputProvider(delegate: AudioOutputProvider) : ForwardingAudioOutputProvider(delegate) {
	private val handler = Handler(Looper.getMainLooper())
	private val releaseParkedTrackRunnable = Runnable { releaseParkedTrack() }
	private var parkedTrack: AudioTrack? = null
	private var parkedTrackIsTrueHd = false

	override fun getFormatSupport(formatConfig: AudioOutputProvider.FormatConfig): AudioOutputProvider.FormatSupport {
		if (!isIecFormat(formatConfig)) return super.getFormatSupport(formatConfig)

		return AudioOutputProvider.FormatSupport.Builder()
			.setFormatSupportLevel(AudioOutputProvider.FORMAT_SUPPORTED_DIRECTLY)
			.build()
	}

	override fun getOutputConfig(formatConfig: AudioOutputProvider.FormatConfig): AudioOutputProvider.OutputConfig {
		if (!isIecFormat(formatConfig)) return super.getOutputConfig(formatConfig)

		val format = formatConfig.format
		val trueHd = format.sampleMimeType == MimeTypes.AUDIO_TRUEHD
		val maxBytesPerSecond = if (trueHd) Ac3Util.TRUEHD_MAX_RATE_BYTES_PER_SECOND else DtsUtil.DTS_HD_MAX_RATE_BYTES_PER_SECOND
		return AudioOutputProvider.OutputConfig.Builder()
			.setEncoding(if (trueHd) C.ENCODING_DOLBY_TRUEHD else C.ENCODING_DTS_HD)
			.setSampleRate(format.sampleRate)
			.setChannelMask(CHANNEL_MASK)
			// Only used by the sink to estimate the buffered duration
			.setBufferSize(maxBytesPerSecond / BUFFER_SIZE_DIVISOR)
			.setAudioAttributes(formatConfig.audioAttributes)
			.setAudioSessionId(formatConfig.audioSessionId)
			.setVirtualDeviceId(formatConfig.virtualDeviceId)
			.build()
	}

	override fun getAudioOutput(config: AudioOutputProvider.OutputConfig): AudioOutput {
		if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N || !isIecOutput(config)) {
			releaseParkedTrack()
			return super.getAudioOutput(config)
		}

		val trueHd = config.encoding == C.ENCODING_DOLBY_TRUEHD

		val audioTrack = takeParkedTrack(trueHd, config.audioSessionId) ?: createAudioTrack(config)
		return IecAudioOutput(
			audioTrack = audioTrack,
			packer = IecPacker.forTrueHd(trueHd),
			contentSampleRate = config.sampleRate,
			onRelease = { track -> parkTrack(track, trueHd) },
		)
	}

	override fun release() {
		releaseParkedTrack()
		super.release()
	}

	private fun isIecFormat(formatConfig: AudioOutputProvider.FormatConfig) =
		Build.VERSION.SDK_INT >= Build.VERSION_CODES.N &&
			!formatConfig.enableTunneling &&
			formatConfig.format.sampleMimeType in MIME_TYPES

	private fun isIecOutput(config: AudioOutputProvider.OutputConfig) = !config.isTunneling && config.encoding in IEC_ENCODINGS

	@RequiresApi(Build.VERSION_CODES.N)
	@Suppress("ThrowsCount")
	private fun createAudioTrack(config: AudioOutputProvider.OutputConfig): AudioTrack {
		val format = AudioFormat.Builder()
			.setEncoding(AudioFormat.ENCODING_IEC61937)
			.setSampleRate(IecPacker.CARRIER_SAMPLE_RATE)
			.setChannelMask(CHANNEL_MASK)
			.build()
		val minBufferSize = AudioTrack.getMinBufferSize(IecPacker.CARRIER_SAMPLE_RATE, CHANNEL_MASK, AudioFormat.ENCODING_IEC61937)
		val sessionId = when (config.audioSessionId) {
			C.AUDIO_SESSION_ID_UNSET -> AudioManager.AUDIO_SESSION_ID_GENERATE
			else -> config.audioSessionId
		}

		val audioTrack = try {
			AudioTrack.Builder()
				.setAudioAttributes(config.audioAttributes.getPlatformAudioAttributes())
				.setAudioFormat(format)
				.setBufferSizeInBytes(maxOf(minBufferSize * 2, MIN_BUFFER_SIZE))
				.setTransferMode(AudioTrack.MODE_STREAM)
				.setSessionId(sessionId)
				.build()
		} catch (err: UnsupportedOperationException) {
			throw AudioOutputProvider.InitializationException(err)
		} catch (err: IllegalArgumentException) {
			throw AudioOutputProvider.InitializationException(err)
		}

		if (audioTrack.state != AudioTrack.STATE_INITIALIZED) {
			audioTrack.release()
			throw AudioOutputProvider.InitializationException(IllegalStateException("IEC 61937 AudioTrack not initialized"))
		}

		Log.i("LitePlayerIEC", "Created IEC 61937 audio track for ${if (config.encoding == C.ENCODING_DOLBY_TRUEHD) "TrueHD" else "DTS"}")
		return audioTrack
	}

	@Synchronized
	private fun parkTrack(audioTrack: AudioTrack, trueHd: Boolean) {
		releaseParkedTrack()
		parkedTrack = audioTrack
		parkedTrackIsTrueHd = trueHd
		handler.postDelayed(releaseParkedTrackRunnable, PARKED_TRACK_TIMEOUT_MS)
	}

	@Synchronized
	private fun takeParkedTrack(trueHd: Boolean, audioSessionId: Int): AudioTrack? {
		val audioTrack = parkedTrack ?: return null
		val sessionMatches = audioSessionId == C.AUDIO_SESSION_ID_UNSET || audioSessionId == audioTrack.audioSessionId
		if (parkedTrackIsTrueHd != trueHd || !sessionMatches) {
			releaseParkedTrack()
			return null
		}

		handler.removeCallbacks(releaseParkedTrackRunnable)
		parkedTrack = null
		Log.i("LitePlayerIEC", "Reusing parked IEC 61937 audio track")
		return audioTrack
	}

	@Synchronized
	private fun releaseParkedTrack() {
		handler.removeCallbacks(releaseParkedTrackRunnable)
		parkedTrack?.let {
			Log.i("LitePlayerIEC", "Releasing parked IEC 61937 audio track")
			it.release()
		}
		parkedTrack = null
	}

	companion object {
		/** The formats this provider packs itself. */
		val MIME_TYPES = setOf(MimeTypes.AUDIO_DTS_HD)

		private const val CHANNEL_MASK = AudioFormat.CHANNEL_OUT_7POINT1_SURROUND
		private const val BUFFER_SIZE_DIVISOR = 4
		private const val PARKED_TRACK_TIMEOUT_MS = 3_000L

		// Room for 8 MAT bursts (160 ms)
		private const val MIN_BUFFER_SIZE = 61_440 * 8

		private val IEC_ENCODINGS = setOf(C.ENCODING_DTS_HD)
	}
}