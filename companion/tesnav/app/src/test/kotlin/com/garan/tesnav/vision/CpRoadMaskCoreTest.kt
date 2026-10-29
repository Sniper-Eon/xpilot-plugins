package com.garan.tesnav.vision

import org.junit.Assert.*
import org.junit.Test

/** Failure cases: tensor layout/overflow/NaN reuses stale pixels; channel IDs
 * become paint labels; malformed IPC mask bypasses limits. Count heads stay independent. */
class CpRoadMaskCoreTest {
    @Test fun layoutsAgreeWithoutInventingPaintSemantics() {
        val a=CpRoadMaskCore.fromScores(intArrayOf(1,2,4,1),
            floatArrayOf(.1f,.7f,.1f,.1f, .1f,.1f,.7f,.1f))!!
        val b=CpRoadMaskCore.fromScores(intArrayOf(1,2,4,0),
            floatArrayOf(.1f,.1f, .7f,.1f, .1f,.7f, .1f,.1f))!!
        assertArrayEquals(byteArrayOf(1,2),a.ids)
        assertArrayEquals(a.ids,b.ids)
        assertEquals("unmapped",a.semantics)
        assertFalse(a.controlEligible)
    }
    @Test fun malformedOutputsNeverBecomeAReportedRoadMask() {
        val s=intArrayOf(1,1,4,1)
        assertNull(CpRoadMaskCore.fromScores(s,floatArrayOf(Float.NaN,0f,0f,1f)))
        assertNull(CpRoadMaskCore.fromScores(s,floatArrayOf(0f,0f,0f,0f)))
        assertNull(CpRoadMaskCore.fromScores(intArrayOf(Int.MAX_VALUE,Int.MAX_VALUE,4,1),FloatArray(0)))
        assertNull(CpRoadMaskCore.fromScores(intArrayOf(1,1,4,9),floatArrayOf(0f,0f,0f,1f)))
        assertNull(CpRoadMaskCore.fromScores(intArrayOf(1,1,3,1),floatArrayOf(0f,0f,1f)))
        assertNull(CpRoadMaskCore.fromScores(s,floatArrayOf(0f,0f,1f)))
        assertNull(CpRoadMaskCore.fromPacket(1,1,byteArrayOf(5),byteArrayOf(100)))
    }
}
