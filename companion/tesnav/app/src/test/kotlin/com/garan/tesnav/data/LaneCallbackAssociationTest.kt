package com.garan.tesnav.data

import com.garan.tesnav.export.NavAssistV2Mapper
import com.garan.tesnav.model.*
import org.junit.Assert.*
import org.junit.Test

/** A callback before keyed guidance must retain its observed engine path without
 * becoming executable until matching guidance; wrong engines/recalculation fail closed.
 */
class LaneCallbackAssociationTest {
    @Test fun callbackBeforeGuidanceSurvivesUntilTheSamePathIsConfirmed() {
        val path=capturedLanePath(42L,null,42L,false)
        assertEquals(42L,path)
        val state=NavigationState(routePlanned=true,navigationMode=NavigationMode.REALTIME,
            acceptedPathId=42L,guidancePathId=null,lanesPathId=path,
            lanesObservedAtMs=3_000,laneCount=1,
            lanes=listOf(LaneState(0,listOf(LaneAction.STRAIGHT),true,0)))
        assertNull(NavAssistV2Mapper.snapshot(state,"sdk",1,4_000,1200).lanes)
        val after=NavAssistV2Mapper.snapshot(state.copy(guidancePathId=42L),"sdk",2,4_000,1200)
        assertEquals(1,after.lanes?.totalCount)
        assertEquals(3_000L,after.lanes?.observedAtMs)
        assertNull(NavAssistV2Mapper.snapshot(state.copy(acceptedPathId=43L,guidancePathId=43L),"sdk",3,4_000,1200).lanes)
    }
    @Test fun unknownConflictingAndRecalculatingRoutesCannotBind() {
        assertNull(capturedLanePath(null,null,42L,false))
        assertNull(capturedLanePath(42L,null,41L,false))
        assertNull(capturedLanePath(42L,41L,42L,false))
        assertNull(capturedLanePath(42L,null,42L,true))
        assertNull(capturedLanePath(42L,null,null,false))
    }
}
