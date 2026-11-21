package com.example.liteplayer.audio

import android.media.AudioDeviceInfo
import android.media.AudioTimestamp
import android.media.AudioTrack
import android.os.Build
import androidx.annotation.OptIn
import androidx.annotation.RequiresApi
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.audio.AudioOutput
import java.nio.ByteBuffer
import java.util.concurrent.CopyOnWriteArraySet

/**
 * [AudioOutput] that packs DTS and TrueHD into IEC 61937 bursts and writes them to an `ENCODING_IEC61937` [AudioTrack].
 * The track runs at the 192 kHz carrier rate, so one carrier frame is 1/192000 s of content.
 *
 * On [release] the track is handed to [onRelease] instead of being released, so the next output can keep using it.
 */
@OptIn(UnstableApi::class)
@RequiresApi(Build.VERSION_CODES.N)
@Suppress("TooManyFunctions") // Required by AudioOutput
internal class IecAudioOutput(
	private val audioTrack: AudioTrack,
	private val packer: IecPacker,
	private val contentSampleRate: Int,
	private val onRelease: (AudioTrack) -> Unit,
) : AudioOutput {
	private val listeners = CopyOnWriteArraySet<AudioOutput.Listener>()
	private val pendingBursts = ArrayDeque<ByteBuffer>()
	private val timestamp = AudioTimestamp()
	private val positionSmoother = IecPositionSmoother()
	private val createdNanos = System.nanoTime()
	private var writtenBytes = 0L
	private var playing = false
	private var positionAdvancing = false
	private var lastTimestampFrames = -1L
	private var lastTimestampNanos = 0L
	private var underrunCount = 0

	override fun play() {
		playing = true
		audioTrack.play()
	}

	override fun pause() {
		playing = false
		positionSmoother.reset()
		audioTrack.pause()
	}

	override fun write(buffer: ByteBuffer, encodedAccessUnitCount: Int, presentationTimeUs: Long): Boolean {
		if (pendingBursts.isEmpty() && buffer.hasRemaining()) packer.pack(buffer, pendingBursts)

		while (pendingBursts.isNotEmpty()) {
			val burst = pendingBursts.first()
			val size = burst.remaining()
			val written = audioTrack.write(burst, size, AudioTrack.WRITE_NON_BLOCKING)
			if (written < 0) throw AudioOutput.WriteException(written, false)
			writtenBytes += written
			if (written < size) return false
			packer.recycle(pendingBursts.removeFirst())
		}

		buffer.position(buffer.limit())
		return true
	}

	override fun flush() {
		pendingBursts.clear()
		packer.reset()
		audioTrack.pause()
		audioTrack.flush()
		writtenBytes = 0
		lastTimestampFrames = -1
		positionAdvancing = false
		positionSmoother.reset()
		if (playing) audioTrack.play()
	}

	override fun stop() = audioTrack.stop()

	override fun release() {
		if (audioTrack.state == AudioTrack.STATE_INITIALIZED) {
			audioTrack.pause()
			audioTrack.flush()
			onRelease(audioTrack)
		} else {
			audioTrack.release()
		}
		listeners.forEach { it.onReleased() }
	}

	override fun getPositionUs(): Long {
		val writtenFrames = writtenBytes / IecPacker.CARRIER_FRAME_BYTES
		var frames = audioTrack.playbackHeadPosition.toUInt().toLong()
		if (playing && readTimestamp()) {
			if (timestamp.framePosition != lastTimestampFrames) {
				lastTimestampFrames = timestamp.framePosition
				lastTimestampNanos = timestamp.nanoTime
			}
			frames = lastTimestampFrames + (System.nanoTime() - lastTimestampNanos) * IecPacker.CARRIER_SAMPLE_RATE / NANOS_PER_SECOND
		}
		val rawPositionUs = minOf(frames, writtenFrames) * MICROS_PER_SECOND / IecPacker.CARRIER_SAMPLE_RATE

		if (!positionAdvancing && rawPositionUs > 0) {
			positionAdvancing = true
			val playoutStartMs = System.currentTimeMillis() - rawPositionUs / MICROS_PER_MILLI
			listeners.forEach { it.onPositionAdvancing(playoutStartMs) }
		}

		val underruns = audioTrack.underrunCount
		if (underruns > underrunCount) listeners.forEach { it.onUnderrun() }
		underrunCount = underruns

		return if (playing) positionSmoother.smooth(rawPositionUs, System.nanoTime()) else rawPositionUs
	}

	// A reused track can still report the previous output's timestamp, so only use newer ones
	private fun readTimestamp() = audioTrack.getTimestamp(timestamp) && timestamp.framePosition > 0 && timestamp.nanoTime > createdNanos

	// Bitstream output cannot change volume or speed
	override fun setVolume(volume: Float) = Unit
	override fun getPlaybackParameters(): PlaybackParameters = PlaybackParameters.DEFAULT
	override fun setPlaybackParameters(playbackParams: PlaybackParameters) = Unit

	override fun isOffloadedPlayback() = false
	override fun getAudioSessionId() = audioTrack.audioSessionId
	override fun getSampleRate() = contentSampleRate
	override fun getBufferSizeInFrames() = audioTrack.bufferSizeInFrames.toLong()
	override fun isStalled() = false
	override fun addListener(listener: AudioOutput.Listener) {
		listeners.add(listener)
	}

	override fun removeListener(listener: AudioOutput.Listener) {
		listeners.remove(listener)
	}

	override fun setOffloadDelayPadding(delayInFrames: Int, paddingInFrames: Int) = Unit
	override fun setOffloadEndOfStream() = Unit
	override fun attachAuxEffect(effectId: Int) = Unit
	override fun setAuxEffectSendLevel(level: Float) = Unit
	override fun setPreferredDevice(preferredDevice: AudioDeviceInfo?) {
		audioTrack.setPreferredDevice(preferredDevice)
	}

	private companion object {
		const val NANOS_PER_SECOND = 1_000_000_000L
		const val MICROS_PER_SECOND = 1_000_000L
		const val MICROS_PER_MILLI = 1_000L
	}
}

/**
 * Smooths the position of an IEC track. Its timestamps occasionally jump by tens of milliseconds and back, which shows
 * as a skip when followed directly. The position is extrapolated on the system clock and slewed towards the track's
 * position by at most 2 % of the elapsed time; large errors and the first second are followed directly.
 */
internal class IecPositionSmoother {
	private var lastPositionUs = -1L
	private var lastNanos = 0L

	fun reset() {
		lastPositionUs = -1
	}

	fun smooth(rawPositionUs: Long, nowNanos: Long): Long {
		var positionUs = rawPositionUs
		if (lastPositionUs >= 0 && rawPositionUs > 0) {
			val elapsedUs = (nowNanos - lastNanos) / NANOS_PER_MICRO
			val predictedUs = lastPositionUs + elapsedUs
			val errorUs = rawPositionUs - predictedUs
			positionUs = if (rawPositionUs < FOLLOW_RAW_UNTIL_US || errorUs !in -RESYNC_THRESHOLD_US..RESYNC_THRESHOLD_US) {
				rawPositionUs
			} else {
				val maxStepUs = elapsedUs / MAX_SLEW_DIVISOR + MIN_STEP_US
				predictedUs + errorUs.coerceIn(-maxStepUs, maxStepUs)
			}
			// Never move backwards while playing
			positionUs = maxOf(positionUs, lastPositionUs)
		}
		lastPositionUs = positionUs
		lastNanos = nowNanos
		return positionUs
	}

	private companion object {
		const val NANOS_PER_MICRO = 1_000L
		const val FOLLOW_RAW_UNTIL_US = 1_000_000L
		const val RESYNC_THRESHOLD_US = 100_000L
		const val MAX_SLEW_DIVISOR = 50
		const val MIN_STEP_US = 200L
	}
}