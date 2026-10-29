package com.garan.tesnav.vision

import org.junit.Assert.*
import org.junit.Test

/** Failure contracts before implementation: a continuous predicted boundary
 * becomes solid without paint; curb-width highlight becomes paint; short or
 * low-confidence trace invents a type; RGB is ignored for white/yellow; a gap
 * at the edge is mislabelled dashed. All results remain read-only estimates.
 */
class CpPaintCoreTest {
    private fun scene(color:Int=0xffeeeeee.toInt(), dashed:Boolean=false, broad:Boolean=false,
                      confidence:Int=240, paint:Boolean=true): CpPaintEstimate {
        val w=640; val h=400; val mw=240; val mh=144
        val rgb=IntArray(w*h) { 0xff303030.toInt() }
        val ids=ByteArray(mw*mh);val conf=ByteArray(mw*mh) { confidence.toByte() }
        for (y in 150..300) {
            val left=(320-(y-150)*1.2).toInt();val right=(320+(y-150)*1.2).toInt()
            val my=y*mh/h
            ids[my*mw+(left*mw/w).coerceIn(0,mw-1)]=1
            ids[my*mw+(right*mw/w).coerceIn(0,mw-1)]=2
            val visible=!dashed || y in 150..178 || y in 193..211 || y in 227..250
            if (paint && visible) for (x in (right-if(broad)20 else 3)..(right+if(broad)20 else 3))
                if(x in 0 until w) rgb[y*w+x]=color
        }
        return CpPaintCore.estimate(rgb,w,h,CpRoadMask(mh,mw,ids,conf))
    }
    @Test fun whiteSolidAndDashedRequireOriginalImageEvidence() {
        val solid=scene().right;val dashed=scene(dashed=true).right
        assertEquals("white",solid.color);assertEquals("continuous",solid.type)
        assertEquals("white",dashed.color);assertEquals("dashed",dashed.type)
        assertEquals("unknown",scene(paint=false).right.type)
        assertFalse(scene().controlEligible)
    }
    @Test fun yellowDependsOnRgbAndAmbiguousLightDoesNotInventPaint() {
        assertEquals("yellow",scene(color=0xffdcbc20.toInt()).right.color)
        assertEquals("unknown",scene(color=0xffa07337.toInt()).right.color)
    }
    @Test fun wideHighlightsAndWeakBoundariesStayUnknown() {
        assertEquals("unknown",scene(broad=true).right.type)
        assertEquals("unknown",scene(confidence=32).right.type)
    }
    @Test fun anAmbiguousColourDoesNotEraseAClearGapPattern() {
        val s=scene(color=0xffa07337.toInt(),dashed=true).right
        assertEquals("unknown",s.color)
        assertEquals("dashed",s.type)
    }
}
