package com.garan.tesnav.export

import com.garan.tesnav.model.*
import com.garan.tesnav.service.AmapAutoBroadcast
import org.junit.Assert.*
import org.junit.Test

/** Before implementation: a held Auto lane list borrows a new guidance clock;
 * expiry never removes its arrows; an unkeyed/wrong-route list gains authority.
 */
class LaneExportFreshnessTest {
    private fun active() = NavigationState(
        navigationProvider="AMAP_AUTO", navigationMode=NavigationMode.REALTIME,
        routePlanned=true, routeMatched=true, navAssistControlAllowed=true,
        acceptedPathId=42L, guidancePathId=42L, currentStepIndex=0, guidanceStepIndex=0,
        latitude=23.1, longitude=113.1, accuracy=4f, bearing=90f, speedKph=36f,
        locationObservedAtMs=12_000, guidanceObservedAtMs=12_000,
        maneuver=NavigationManeuver.TURN_RIGHT,
        autoDisplayLanesPathId=42L, lanesObservedAtMs=10_000,
        autoDisplayLanes=listOf(LaneState(0,listOf(LaneAction.RIGHT),true,3)),
        laneCount=1,
    )
    @Test fun heldAutoLaneKeepsItsOwnCallbackTimeAcrossExports() {
        val state=active()
        val one=NavAssistV2Mapper.snapshot(state,"auto",1,12_000,1200)
        val two=NavAssistV2Mapper.snapshot(state.copy(guidanceObservedAtMs=15_000),"auto",2,15_000,1200)
        assertEquals(10_000L,one.lanes?.observedAtMs)
        assertEquals(10_000L,two.lanes?.observedAtMs)
    }
    @Test fun unkeyedWrongRouteAndRecalculationCannotExportLanes() {
        for (state in listOf(active().copy(autoDisplayLanesPathId=null),
            active().copy(autoDisplayLanesPathId=41),active().copy(guidancePathId=41),
            active().copy(routeRecalculating=true))) {
            assertNull(NavAssistV2Mapper.snapshot(state,"auto",1,12_000,1200).lanes)
        }
    }
    @Test fun missingAndFutureObservationTimeCannotBecomeFreshFromGuidance() {
        for (stamp in listOf(null,20_000L)) {
            val state=active().copy(lanesObservedAtMs=stamp)
            assertNull(NavAssistV2Mapper.snapshot(state,"auto",1,12_000,1200).lanes)
        }
    }
}
