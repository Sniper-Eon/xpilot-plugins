package com.jixiexiaoge.drivingassist.data

import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.junit.Assert.*
import org.junit.Test

class CompactTelemetryTest {
    private fun packet(seq: Int = 1): ByteArray {
        val b = ByteBuffer.allocate(73).order(ByteOrder.LITTLE_ENDIAN)
        b.put("CVS1".toByteArray()).put(1).put(0).putShort(seq.toShort())
        b.putFloat(12.5f)
        b.putFloat(8 + 16, -7.5f)
        b.put(8 + 32, 1) // actual leftBlindspot, not a lane-distance inference
        b.put(8 + 39, 1)
        return b.array()
    }

    @Test fun decodesNativeFlagsAndLittleEndianFloats() {
        val row = CompactTelemetry.decode(packet())!!
        assertEquals(12.5f, row.carState.vEgo, 0.001f)
        assertEquals(-7.5f, row.carState.steeringAngleDeg, 0.001f)
        assertTrue(row.carState.leftBlindspot)
        assertFalse(row.carState.rightBlindspot)
        assertTrue(row.carState.leftBlinker)
        assertFalse(row.carState.rightBlinker)
    }

    @Test fun rejectsTruncatedUnknownAndNonFiniteFrames() {
        assertNull(CompactTelemetry.decode(packet().copyOf(72)))
        assertNull(CompactTelemetry.decode(packet().also { it[4] = 9 }))
        assertNull(CompactTelemetry.decode(packet().also { it[5] = 1 }))
        val bad = packet()
        ByteBuffer.wrap(bad).order(ByteOrder.LITTLE_ENDIAN).putFloat(8, Float.NaN)
        assertNull(CompactTelemetry.decode(bad))
    }

    @Test fun duplicateOrReorderedPacketsDoNotRenewFreshness() {
        val state = FreshTelemetry()
        assertTrue(state.accept(packet(65535), 100L))
        assertFalse(state.accept(packet(65535), 800L))
        assertFalse(state.accept(packet(65534), 800L))
        assertNull(state.current(1100L))
        assertTrue(state.accept(packet(0), 1200L))
        assertNotNull(state.current(1200L))
        state.clear()
        assertNull(state.current(1200L))
        assertTrue(state.accept(packet(1), 1200L))
    }
}
