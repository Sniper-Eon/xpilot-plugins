package com.jixiexiaoge.drivingassist.data

import java.nio.ByteBuffer
import java.nio.ByteOrder

/** CP compact carState v1. No invented distances or side radar tracks. */
object CompactTelemetry {
    data class Row(val sequence: Int, val carState: CarState)

    fun decode(frame: ByteArray): Row? {
        if (frame.size != 73 || !frame.copyOfRange(0, 4).contentEquals("CVS1".toByteArray()) ||
            frame[4].toInt() != 1 || frame[5].toInt() != 0) return null
        val b = ByteBuffer.wrap(frame).order(ByteOrder.LITTLE_ENDIAN)
        val speed = b.getFloat(8)
        val steering = b.getFloat(24)
        if (!speed.isFinite() || !steering.isFinite() || speed !in 0f..120f ||
            steering !in -2000f..2000f) return null
        val flagOffsets = listOf(8 + 32, 8 + 33, 8 + 39, 8 + 40)
        if (flagOffsets.any { frame[it].toInt() !in 0..1 }) return null
        return Row(b.getShort(6).toInt() and 65535, CarState(
            vEgo = speed, steeringAngleDeg = steering,
            leftBlindspot = frame[40].toInt() == 1,
            rightBlindspot = frame[41].toInt() == 1,
            leftBlinker = frame[47].toInt() == 1,
            rightBlinker = frame[48].toInt() == 1,
        ))
    }
}

/** Only accepted vehicle packets renew age; hello, ping and repeats never do. */
class FreshTelemetry {
    private var row: CompactTelemetry.Row? = null
    private var receivedAt = 0L

    @Synchronized fun accept(bytes: ByteArray, nowMs: Long): Boolean {
        val next = CompactTelemetry.decode(bytes) ?: return false
        row?.let {
            val advance = (next.sequence - it.sequence) and 65535
            if (advance !in 1..32767) return false
        }
        row = next
        receivedAt = nowMs
        return true
    }

    @Synchronized fun current(nowMs: Long): CarState? =
        row?.carState?.takeIf { nowMs - receivedAt in 0 until 1000 }

    @Synchronized fun clear() {
        row = null
        receivedAt = 0L
    }
}
