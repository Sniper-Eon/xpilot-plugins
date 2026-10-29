package com.garan.tesnav.vision

import org.junit.Assert.*
import org.junit.Test

class CpLaneCoreTest {
    @Test fun classesAreCandidatesNotAbsoluteMapLanes() {
        val r = CpLaneCore.decode(floatArrayOf(0f,1f,4f,0f,0f,1f,4f,0f), "vlaneDay.mnn")!!
        assertEquals(2, r.laneNumber)
        assertEquals(3, r.laneCount)
        assertEquals("visibleCorridor", r.scope)
        assertFalse(r.control_eligible)
    }
    @Test fun invalidUnknownOrTiedScoresAreUnavailable() {
        for (scores in listOf(FloatArray(8), floatArrayOf(4f,0f,0f,0f,0f,1f,4f,0f),
            FloatArray(8) { Float.NaN }, floatArrayOf(1f))) {
            assertNull(CpLaneCore.decode(scores,"vlaneDay.mnn"))
        }
    }
    @Test fun lumaMatchesLimitedRangeI420AndKeepsPixelOrder() {
        val y=CpLaneCore.luma(intArrayOf(0xff000000.toInt(),0xffffffff.toInt()))
        assertEquals(16,y[0].toInt() and 255)
        assertEquals(235,y[1].toInt() and 255)
    }
}
