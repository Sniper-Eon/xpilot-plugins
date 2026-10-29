package com.garan.tesnav.vision

import org.junit.Assert.*
import org.junit.Test

/** Failure contracts: one visible dash segment is mistaken for solid; stopped
 * vehicle/time alone confirms solid; missing/currently invalid imagery reuses
 * old type; stream, capture order or boundary changes retain unrelated history. */
class CpPaintTrackerTest {
    private fun continuous()=CpPaintEstimate(right=CpPaintSide("white","continuous",.9f,"imageEstimate",25,25))
    @Test fun solidRequiresFreshContinuousObservationsAcrossVehicleMotion() {
        val t=CpPaintTracker()
        var result=t.update(continuous(),"a",1_000_000_000,10.0)
        assertEquals("unknown",result.right.type)
        for(i in 1..8) result=t.update(continuous(),"a",1_000_000_000L+i*200_000_000L,10.0)
        assertEquals("solid",result.right.type)
        assertEquals("unknown",t.update(CpPaintEstimate(),"a",2_800_000_000,10.0).right.type)
    }
    @Test fun stationaryAndReconnectedInputsDoNotAccumulatePermission() {
        val t=CpPaintTracker()
        for(i in 0..20)assertEquals("unknown",t.update(continuous(),"a",1_000_000_000L+i*200_000_000L,0.0).right.type)
        assertEquals("unknown",t.update(continuous(),"b",6_000_000_000,10.0).right.type)
        assertEquals("unknown",t.update(continuous(),"b",6_000_000_000,10.0).right.type)
        assertFalse(t.update(continuous(),"b",7_000_000_000,10.0).controlEligible)
    }
    @Test fun genuineVisibleGapPatternCanBeReportedWithoutSolidHistory() {
        val t=CpPaintTracker()
        val d=CpPaintEstimate(right=CpPaintSide("white","dashed",.9f,"imageEstimate",15,25))
        assertEquals("dashed",t.update(d,"a",1_000_000_000,10.0).right.type)
    }
}
