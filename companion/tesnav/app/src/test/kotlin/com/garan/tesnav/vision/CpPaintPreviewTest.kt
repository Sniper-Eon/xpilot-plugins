package com.garan.tesnav.vision

import org.junit.Assert.*
import org.junit.Test

/** Failure contracts: an ACK/UI receipt renews old image age; missing capture
 * age is presented as current; raw continuous fragment is labelled solid. */
class CpPaintPreviewTest {
    @Test fun originalAgeBoundsDisplayLifetime() {
        assertEquals(700L,CpPaintPreview.remaining(0.0,100,null))
        assertEquals(200L,CpPaintPreview.remaining(500.0,200,100.0))
        assertEquals(0L,CpPaintPreview.remaining(null,100,null))
        assertEquals(0L,CpPaintPreview.remaining(650.0,100,null))
        assertEquals(0L,CpPaintPreview.remaining(Double.NaN,100,null))
    }
    @Test fun debugBoundaryColourNeverMeansPhysicalPaintColour() {
        val p=CpPaintEstimate(right=CpPaintSide("unknown","continuous",.9f))
        val label=CpPaintPreview.text(p)
        assertFalse(label.contains("实线"))
        assertTrue(label.contains("连续片段"))
        assertTrue(label.contains("估计"))
    }
}
