/*
 * The DTS type IV and TrueHD MAT packing is derived from FFmpeg's libavformat/spdifenc.c:
 * Copyright (c) 2009 Bartlomiej Wolowiec
 * Copyright (c) 2010, 2020 Anssi Hannula
 * Copyright (c) 2010 Carl Eugen Hoyos
 * Licensed under the GNU Lesser General Public License version 2.1 or later.
 */
package com.example.liteplayer.audio

import android.util.Log
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Packs compressed audio into IEC 61937 bursts for an AudioTrack opened with `ENCODING_IEC61937` at 192 kHz with 8
 * channels. Bursts are little-endian 16-bit words, which is what the platform expects for that encoding.
 */
internal sealed class IecPacker {
	private val freeBursts = ArrayDeque<ByteBuffer>()

	/**
	 * Packs the access units in [input] (position to limit, the buffer is not consumed) and appends the bursts that
	 * are complete to [output].
	 */
	abstract fun pack(input: ByteBuffer, output: MutableCollection<ByteBuffer>)

	/** Drops all partially packed data, for use after a seek. */
	abstract fun reset()

	/** Hands a fully written burst back so its memory can be reused. */
	fun recycle(burst: ByteBuffer) {
		if (freeBursts.size < MAX_FREE_BURSTS) freeBursts.addLast(burst)
	}

	/**
	 * Writes a burst of [period] bytes: the preamble, [payload] (big-endian bytes, swapped into little-endian words) and
	 * zero padding.
	 */
	protected fun createBurst(dataType: Int, lengthCode: Int, payload: List<ByteBuffer>, period: Int): ByteBuffer {
		val burst = obtainBurst(period)
		burst.putShort(SYNC_WORD_1)
		burst.putShort(SYNC_WORD_2)
		burst.putShort(dataType.toShort())
		burst.putShort(lengthCode.toShort())
		for (part in payload) {
			val source = part.duplicate().order(ByteOrder.BIG_ENDIAN)
			while (source.remaining() >= 2) burst.putShort(source.getShort())
			// A final lone byte is MSB aligned
			if (source.hasRemaining()) burst.putShort((source.get().toUByte().toInt() shl Byte.SIZE_BITS).toShort())
		}
		while (burst.hasRemaining()) burst.put(0)
		burst.flip()
		return burst
	}

	private fun obtainBurst(size: Int): ByteBuffer {
		val iterator = freeBursts.iterator()
		while (iterator.hasNext()) {
			val buffer = iterator.next()
			if (buffer.capacity() >= size) {
				iterator.remove()
				buffer.clear().limit(size)
				return buffer
			}
		}
		return ByteBuffer.allocateDirect(size).order(ByteOrder.LITTLE_ENDIAN)
	}

	companion object {
		const val CARRIER_SAMPLE_RATE = 192_000
		const val CARRIER_FRAME_BYTES = 16
		const val BURST_HEADER_SIZE = 8

		private const val SYNC_WORD_1: Short = 0xF872.toShort()
		private const val SYNC_WORD_2: Short = 0x4E1F
		private const val MAX_FREE_BURSTS = 16

		fun forTrueHd(trueHd: Boolean): IecPacker = if (trueHd) TrueHdIecPacker() else DtsHdIecPacker()
	}
}

/** DTS and DTS-HD as IEC 61937 type IV bursts at the 768 kHz rate (FFmpeg `-dtshd_rate 768000`). */
@Suppress("MagicNumber")
internal class DtsHdIecPacker : IecPacker() {
	private val header = ByteArray(START_CODE.size + 2).also { START_CODE.copyInto(it) }
	private var coreOnlyFramesLeft = 0
	private var loggedInvalidFrame = false

	override fun pack(input: ByteBuffer, output: MutableCollection<ByteBuffer>) {
		val frame = input.duplicate().order(ByteOrder.BIG_ENDIAN)
		val position = frame.position()
		val size = frame.remaining()
		if (size < MIN_FRAME_SIZE || frame.getInt(position) != CORE_SYNC_WORD) return logInvalidFrame("no core sync word")

		val blocks = ((frame.getShort(position + 4).toInt() shr 2) and 0x7f) + 1
		val coreSize = ((frame.getInt(position + 4) shr 4) and 0x3fff) + 1
		val sampleRate = SAMPLE_RATES[(frame.get(position + 8).toInt() shr 2) and 0x0f]
		if (sampleRate == 0) return logInvalidFrame("unknown sample rate")

		val period = DTS_HD_RATE * (blocks shl 5) / sampleRate
		val subtype = Integer.numberOfTrailingZeros(period) - 9
		if (Integer.bitCount(period) != 1 || subtype !in 0..5) return logInvalidFrame("impossible repetition period $period")

		// Strip the HD part for a while if the frame does not fit in the burst
		val burstSize = period * 4
		if (header.size + size > burstSize - BURST_HEADER_SIZE) {
			if (coreOnlyFramesLeft == 0) Log.w("LitePlayerIEC", "DTS-HD bitrate too high, temporarily sending core only")
			coreOnlyFramesLeft = sampleRate * FALLBACK_SECONDS / (blocks shl 5)
		}
		var payloadSize = size
		if (coreOnlyFramesLeft > 0 && coreSize <= size) {
			payloadSize = coreSize
			coreOnlyFramesLeft--
		}

		header[START_CODE.size] = (payloadSize shr 8).toByte()
		header[START_CODE.size + 1] = payloadSize.toByte()
		val payload = frame.duplicate().apply { limit(position + payloadSize) }
		val outBytes = header.size + payloadSize
		// Align so that (length_code & 0xf) == 0x8, as FFmpeg does
		val lengthCode = ((outBytes + 0x8 + 0xf) and 0xf.inv()) - 0x8
		output.add(createBurst(DATA_TYPE_DTS_HD or (subtype shl 8), lengthCode, listOf(ByteBuffer.wrap(header), payload), burstSize))
	}

	override fun reset() {
		coreOnlyFramesLeft = 0
	}

	private fun logInvalidFrame(reason: String) {
		if (loggedInvalidFrame) return
		loggedInvalidFrame = true
		Log.w("LitePlayerIEC", "Dropping DTS frame: $reason")
	}

	private companion object {
		const val DATA_TYPE_DTS_HD = 0x11
		const val DTS_HD_RATE = 768_000
		const val CORE_SYNC_WORD = 0x7FFE8001
		const val MIN_FRAME_SIZE = 9
		const val FALLBACK_SECONDS = 60
		val START_CODE = byteArrayOf(0x01, 0, 0, 0, 0, 0, 0, 0, 0xfe.toByte(), 0xfe.toByte())
		val SAMPLE_RATES = intArrayOf(0, 8000, 16000, 32000, 0, 0, 11025, 22050, 44100, 0, 0, 12000, 24000, 48000, 0, 0)
	}
}

/** TrueHD access units collected into MAT frames (IEC 61937 data type 0x16). */
@Suppress("MagicNumber")
internal class TrueHdIecPacker : IecPacker() {
	private val matFrame = ByteArray(MAT_FRAME_SIZE)
	private val matFrameBuffer = ByteBuffer.wrap(matFrame)
	private var filled = 0
	private var samplesPerFrame = 0
	private var previousInputTiming = 0
	private var previousFrameSize = 0
	private var outputTiming = 0
	private var outputTimingValid = false
	private var outputInputDelta = 0

	private class AccessUnitInfo(val inputTiming: Int, val outputTiming: Int?)

	override fun pack(input: ByteBuffer, output: MutableCollection<ByteBuffer>) {
		// Media3 delivers several access units per buffer
		val data = input.duplicate().order(ByteOrder.BIG_ENDIAN)
		var offset = data.position()
		while (offset + MIN_ACCESS_UNIT_SIZE <= data.limit()) {
			val size = ((data.get(offset).toInt() and 0x0f shl 8) or (data.get(offset + 1).toInt() and 0xff)) * 2
			if (size < MIN_ACCESS_UNIT_SIZE || offset + size > data.limit()) {
				Log.w("LitePlayerIEC", "Dropping TrueHD buffer: invalid access unit size $size")
				return
			}
			val accessUnit = data.duplicate().order(ByteOrder.BIG_ENDIAN).apply {
				limit(offset + size)
				position(offset)
			}
			packAccessUnit(accessUnit, output)
			offset += size
		}
	}

	override fun reset() {
		filled = 0
		samplesPerFrame = 0
		previousFrameSize = 0
		outputTimingValid = false
	}

	private fun packAccessUnit(accessUnit: ByteBuffer, output: MutableCollection<ByteBuffer>) {
		val info = parseAccessUnit(accessUnit) ?: return
		if (samplesPerFrame == 0) return // No major sync seen yet

		val padding = computePadding(info)
		if (outputTimingValid) outputInputDelta = ((outputTiming - samplesPerFrame) - info.inputTiming).toShort().toInt()

		previousFrameSize = fillMatFrames(accessUnit, padding, output)
		previousInputTiming = info.inputTiming
	}

	/** Reads the input timing, and from a major sync the frame size and (if present) the output timing. */
	private fun parseAccessUnit(accessUnit: ByteBuffer): AccessUnitInfo? {
		val start = accessUnit.position()
		val inputTiming = accessUnit.getShort(start + 2).toInt() and 0xffff
		val data = start + 4
		val size = accessUnit.remaining() - 4
		if (size < 6 || accessUnit.getInt(data) ushr 8 != MAJOR_SYNC) return AccessUnitInfo(inputTiming, null)

		val format = accessUnit.get(data + 3).toInt() and 0xff
		val rateBits = when (format) {
			FORMAT_TRUEHD -> (accessUnit.get(data + 4).toInt() and 0xff) shr 4
			FORMAT_MLP -> (accessUnit.get(data + 5).toInt() and 0xff) shr 4
			else -> return null
		}
		samplesPerFrame = 40 shl (rateBits and 3)
		if (size < 27) return AccessUnitInfo(inputTiming, null)

		var majorSyncSize = 28
		if (format == FORMAT_TRUEHD && accessUnit.get(data + 25).toInt() and 1 != 0) {
			majorSyncSize += 2 + ((accessUnit.get(data + 26).toInt() and 0xff) shr 4) * 2
		}
		if (majorSyncSize > size) return AccessUnitInfo(inputTiming, null)

		val substreams = (accessUnit.get(data + 16).toInt() and 0xff) shr 4
		val bits = BitReader(accessUnit, data + majorSyncSize, size - majorSyncSize)
		return AccessUnitInfo(inputTiming, readOutputTiming(bits, substreams))
	}

	/** Output timing from the first substream's restart header, as in FFmpeg's `truehd_parse_access_unit`. */
	private fun readOutputTiming(bits: BitReader, substreams: Int): Int? {
		if (substreams <= 0) return null
		repeat(substreams) {
			if (bits.left < 16) return null
			val extraWord = bits.readBit()
			bits.skip(15)
			if (extraWord) {
				if (bits.left < 16) return null
				bits.skip(16)
			}
		}
		val blockHeaderExists = bits.left >= 1 && bits.readBit()
		val restartHeaderExists = blockHeaderExists && bits.left >= 1 && bits.readBit()
		if (!restartHeaderExists || bits.left < 13 + 1 + 16) return null
		if (bits.read(13) != RESTART_SYNC_WORD) return null
		bits.skip(1) // noise_type
		return bits.read(16)
	}

	/** Bytes of zero padding to insert before this access unit so the MAT timing matches the input timing. */
	private fun computePadding(info: AccessUnitInfo): Int {
		var padding = 0
		var discontinuity = false
		outputTiming = (outputTiming + samplesPerFrame) and 0xffff
		if (info.outputTiming != null) {
			if (outputTimingValid && info.outputTiming != outputTiming) {
				discontinuity = true
				val currentDelta = ((info.outputTiming - samplesPerFrame) - info.inputTiming).toShort().toInt()
				val previousPadding = if (previousFrameSize != 0) NOMINAL_AU_SPACING - previousFrameSize else 0
				padding = previousPadding + (outputInputDelta - currentDelta) * (NOMINAL_AU_SPACING / samplesPerFrame)
			}
			outputTiming = info.outputTiming
			outputTimingValid = true
		}
		if (previousFrameSize != 0 && !discontinuity) {
			val deltaSamples = (info.inputTiming - previousInputTiming) and 0xffff
			padding = deltaSamples * NOMINAL_AU_SPACING / samplesPerFrame - previousFrameSize
		}
		if (padding !in 0..MAX_PADDING) {
			Log.w("LitePlayerIEC", "Ignoring unusual TrueHD timing, padding $padding")
			padding = 0
		}
		return padding
	}

	/** Copies padding and data into MAT frames, emitting each frame once full; returns the space the unit used. */
	private fun fillMatFrames(accessUnit: ByteBuffer, initialPadding: Int, output: MutableCollection<ByteBuffer>): Int {
		var padding = initialPadding
		var frameSize = accessUnit.remaining()
		var next = MAT_CODE_POSITIONS.indexOfFirst { filled <= it }
		check(next >= 0) { "MAT frame overfilled ($filled)" }

		while (padding > 0 || accessUnit.hasRemaining() || MAT_CODE_POSITIONS[next] == filled) {
			if (MAT_CODE_POSITIONS[next] == filled) {
				val code = MAT_CODES[next]
				code.copyInto(matFrame, filled)
				filled += code.size
				var codeRemaining = code.size
				next++
				if (next == MAT_CODES.size) {
					next = 0
					output.add(createBurst(DATA_TYPE_TRUEHD, MAT_FRAME_SIZE, listOf(matFrameBuffer), MAT_BURST_SIZE))
					filled = 0
					// The gap between MAT frames counts as well
					codeRemaining += MAT_BURST_SIZE - MAT_FRAME_SIZE
				}
				// The MAT code counts as padding, the rest of it as part of the frame
				val countedAsPadding = minOf(padding, codeRemaining)
				padding -= countedAsPadding
				frameSize += codeRemaining - countedAsPadding
			}

			val space = MAT_CODE_POSITIONS[next] - filled
			if (padding > 0) {
				val count = minOf(space, padding)
				matFrame.fill(0, filled, filled + count)
				filled += count
				padding -= count
				if (padding > 0) continue
			}
			if (accessUnit.hasRemaining()) {
				val count = minOf(MAT_CODE_POSITIONS[next] - filled, accessUnit.remaining())
				accessUnit.get(matFrame, filled, count)
				filled += count
			}
		}
		return frameSize
	}

	/** MSB-first bit reader over part of a buffer. */
	private class BitReader(private val buffer: ByteBuffer, private val offset: Int, length: Int) {
		private val end = length * 8
		private var position = 0

		val left get() = end - position

		fun skip(count: Int) {
			position += count
		}

		fun readBit() = read(1) == 1

		fun read(count: Int): Int {
			var value = 0
			repeat(count) {
				val byte = buffer.get(offset + (position shr 3)).toInt()
				value = (value shl 1) or ((byte shr (7 - (position and 7))) and 1)
				position++
			}
			return value
		}
	}

	private companion object {
		const val DATA_TYPE_TRUEHD = 0x16
		const val MAT_BURST_SIZE = 61440
		const val MAT_FRAME_SIZE = 61424
		const val MAX_PADDING = MAT_FRAME_SIZE * 2
		const val MIN_ACCESS_UNIT_SIZE = 10

		// One 48 kHz frame lasts 1/1200 s; at 768 kHz * 4 bytes that is 2560 bytes (the same for 44.1 kHz).
		const val NOMINAL_AU_SPACING = 2560
		const val MAJOR_SYNC = 0xf8726f
		const val FORMAT_TRUEHD = 0xba
		const val FORMAT_MLP = 0xbb
		const val RESTART_SYNC_WORD = 0x31ea shr 1

		val MAT_START_CODE = byteArrayOf(
			0x07, 0x9E.toByte(), 0x00, 0x03, 0x84.toByte(), 0x01, 0x01, 0x01, 0x80.toByte(), 0x00,
			0x56, 0xA5.toByte(), 0x3B, 0xF4.toByte(), 0x81.toByte(), 0x83.toByte(), 0x49, 0x80.toByte(), 0x77, 0xE0.toByte(),
		)
		val MAT_MIDDLE_CODE = byteArrayOf(
			0xC3.toByte(), 0xC1.toByte(), 0x42, 0x49, 0x3B, 0xFA.toByte(), 0x82.toByte(), 0x83.toByte(), 0x49, 0x80.toByte(),
			0x77, 0xE0.toByte(),
		)
		val MAT_END_CODE = byteArrayOf(
			0xC3.toByte(), 0xC2.toByte(), 0xC0.toByte(), 0xC4.toByte(), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x97.toByte(), 0x11,
		)
		val MAT_CODES = arrayOf(MAT_START_CODE, MAT_MIDDLE_CODE, MAT_END_CODE)
		val MAT_CODE_POSITIONS = intArrayOf(0, 30708, MAT_FRAME_SIZE - MAT_END_CODE.size)
	}
}