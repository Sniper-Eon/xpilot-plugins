package com.garan.tesnav.service

import com.garan.tesnav.export.NavAssistV2Mapper
import com.garan.tesnav.model.*
import org.junit.Assert.*
import org.junit.Test

class AmapAutoCpCompatibilityTest {
    private fun active() = AmapAutoBroadcast.navigation(null, null,
        mapOf("ICON" to 3, "ROAD_TYPE" to 1, "ROUTE_ALL_DIS" to 2000,
            "SEG_REMAIN_DIS" to 90, "CAR_LATITUDE" to 31.2,
            "CAR_LONGITUDE" to 121.5, "CAR_ACCURACY" to 5),
        10_000, 1_000, 3_000)

    @Test fun `receive only the three CP-compatible send actions`() {
        assertEquals(setOf("AUTONAVI_STANDARD_BROADCAST_SEND", "AMAP_BROADCAST_SEND",
            "AUTONAVI_BROADCAST_SEND"), AmapAutoCpCompatibility.SEND_ACTIONS)
        assertFalse(AmapAutoCpCompatibility.SEND_ACTIONS.contains("AUTONAVI_STANDARD_BROADCAST_RECV"))
    }

    @Test fun `next Auto icon keeps its own namespace through the TesNav wire mapper`() {
        val state = active()
        val updated = AmapAutoCpCompatibility.enrich(state, mapOf(
            "NEXT_NEXT_TURN_ICON" to "11", "NEXT_SEG_REMAIN_DIS" to "350"))
        assertEquals(NavigationManeuver.KEEP_RIGHT, updated.nextManeuver)
        assertEquals(350, updated.nextManeuverDistanceMeters)
        assertEquals(state, updated.copy(nextManeuver = state.nextManeuver,
            nextManeuverDistanceMeters = state.nextManeuverDistanceMeters))
        val wire = NavAssistV2Mapper.snapshot(updated, "cp-amap", 1, 10_000, 500)
        assertEquals("keep_right", wire.guidance?.nextManeuver)
        assertEquals(350, wire.guidance?.nextManeuverDistanceM)
    }

    @Test fun `missing malformed and unrecognized next turn clears prior hint`() {
        val old = active().copy(nextManeuver = NavigationManeuver.TURN_LEFT,
            nextManeuverDistanceMeters = 600)
        for (extras in listOf(emptyMap(), mapOf("NEXT_NEXT_TURN_ICON" to 999,
            "NEXT_SEG_REMAIN_DIS" to 30), mapOf("NEXT_NEXT_TURN_ICON" to 2,
            "NEXT_SEG_REMAIN_DIS" to -1), mapOf("NEXT_NEXT_TURN_ICON" to 2.5,
            "NEXT_SEG_REMAIN_DIS" to 30), mapOf("NEXT_NEXT_TURN_ICON" to 2,
            "NEXT_SEG_REMAIN_DIS" to Double.NaN))) {
            val state = AmapAutoCpCompatibility.enrich(old, extras)
            assertEquals(NavigationManeuver.NONE, state.nextManeuver)
            assertNull(state.nextManeuverDistanceMeters)
        }
    }

    @Test fun `camera fields are optional bounded observations and never route permission`() {
        val original = active()
        val state = AmapAutoCpCompatibility.enrich(original, mapOf(
            "CAMERA_TYPE" to 0, "CAMERA_DIST" to "450", "CAMERA_SPEED" to 60))
        assertEquals(CameraType.SPEED, state.cameras.single().type)
        assertEquals(450, state.cameras.single().distanceMeters)
        assertEquals(60, state.cameras.single().limitSpeedKph)
        assertTrue(state.hasSpeedCameraAhead)
        assertEquals(original, state.copy(cameras = original.cameras,
            hasSpeedCameraAhead = original.hasSpeedCameraAhead))
        for (extras in listOf(emptyMap(), mapOf("CAMERA_TYPE" to 0),
            mapOf("CAMERA_TYPE" to 999, "CAMERA_DIST" to 10),
            mapOf("CAMERA_TYPE" to 0, "CAMERA_DIST" to Double.POSITIVE_INFINITY))) {
            val cleared = AmapAutoCpCompatibility.enrich(state, extras)
            assertTrue(cleared.cameras.isEmpty())
            assertFalse(cleared.hasSpeedCameraAhead)
        }
        assertNull(AmapAutoCpCompatibility.enrich(original, mapOf("CAMERA_TYPE" to 0,
            "CAMERA_DIST" to 10, "CAMERA_SPEED" to 999)).cameras.single().limitSpeedKph)
    }

    @Test fun `confirmed arrival clears all route facts without refreshing observation clocks`() {
        val original = active().copy(navAssistControlAllowed = true,
            lanes = listOf(LaneState(0, recommended = true)), laneCount = 1,
            lanesPathId = active().acceptedPathId, lanesObservedAtMs = 10_000,
            autoDisplayLanes = listOf(LaneState(0)), autoDisplayLanesPathId = active().acceptedPathId,
            nextManeuver = NavigationManeuver.TURN_LEFT, nextManeuverDistanceMeters = 20)
        val ended = AmapAutoCpCompatibility.lifecycle(original,
            mapOf("KEY_TYPE" to "10019", "EXTRA_STATE" to "39"))!!
        assertEquals(NavigationMode.ARRIVED, ended.navigationMode)
        assertFalse(ended.routePlanned)
        assertFalse(ended.navAssistControlAllowed)
        assertFalse(ended.routeMatched == true)
        assertNull(ended.acceptedPathId)
        assertNull(ended.guidancePathId)
        assertNull(ended.lanesPathId)
        assertNull(ended.guidanceStepIndex)
        assertNull(ended.lanesObservedAtMs)
        assertTrue(ended.lanes.isEmpty())
        assertTrue(ended.autoDisplayLanes.isEmpty())
        assertEquals(NavigationManeuver.NONE, ended.nextManeuver)
        assertEquals(original.locationObservedAtMs, ended.locationObservedAtMs)
        assertNull(ended.guidanceObservedAtMs)
        val wire = NavAssistV2Mapper.snapshot(ended, "arrival", 2, 10_100, 500)
        assertFalse(wire.routeActive)
    }

    @Test fun `unknown lifecycle cannot start stop or refresh navigation`() {
        val original = active()
        for (extras in listOf(emptyMap(), mapOf("KEY_TYPE" to 10042, "NAVI_STATUS" to 1),
            mapOf("KEY_TYPE" to 10019, "EXTRA_STATE" to 1))) {
            assertEquals(original, AmapAutoCpCompatibility.lifecycle(original, extras))
            assertNull(AmapAutoCpCompatibility.lifecycle(null, extras))
        }
        assertNull(AmapAutoCpCompatibility.lifecycle(null,
            mapOf("KEY_TYPE" to 10019, "EXTRA_STATE" to 39)))
    }
}
