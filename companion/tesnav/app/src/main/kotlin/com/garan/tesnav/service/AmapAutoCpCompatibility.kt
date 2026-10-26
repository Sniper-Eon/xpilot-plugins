package com.garan.tesnav.service

import com.garan.tesnav.model.CameraState
import com.garan.tesnav.model.CameraType
import com.garan.tesnav.model.NavigationManeuver
import com.garan.tesnav.model.NavigationMode
import com.garan.tesnav.model.NavigationState
import com.garan.tesnav.util.NavigationMappers

/** CP public AMap broadcast contracts projected into TesNav, without CP transport or control code. */
internal object AmapAutoCpCompatibility {
    val SEND_ACTIONS = setOf("AUTONAVI_STANDARD_BROADCAST_SEND", "AMAP_BROADCAST_SEND",
        "AUTONAVI_BROADCAST_SEND")

    /** Called only for a new 10001 observation; never retimes retained facts. */
    fun enrich(state: NavigationState, extras: Map<String, Any?>): NavigationState {
        val nextIcon = integer(extras["NEXT_NEXT_TURN_ICON"])
        val nextDistance = integer(extras["NEXT_SEG_REMAIN_DIS"])?.takeIf { it in 0..100_000 }
        val next = AmapAutoBroadcast.autoManeuver(nextIcon, state.currentRoadClass)
            .takeIf { state.routePlanned && nextDistance != null &&
                it !in setOf(NavigationManeuver.NONE, NavigationManeuver.UNKNOWN) }
        val cameraType = integer(extras["CAMERA_TYPE"])?.let(NavigationMappers::cameraType)
            ?.takeUnless { it == CameraType.UNKNOWN }
        val cameraDistance = integer(extras["CAMERA_DIST"])?.takeIf { it in 0..100_000 }
        val cameras = if (state.routePlanned && cameraType != null && cameraDistance != null)
            listOf(CameraState(type = cameraType, distanceMeters = cameraDistance,
                limitSpeedKph = integer(extras["CAMERA_SPEED"])?.let(NavigationMappers::validSpeedLimit)))
            else emptyList()
        return state.copy(
            nextManeuver = next ?: NavigationManeuver.NONE,
            nextManeuverDistanceMeters = nextDistance.takeIf { next != null },
            cameras = cameras,
            hasSpeedCameraAhead = cameras.any { it.type in setOf(CameraType.SPEED,
                CameraType.INTERVAL_START, CameraType.INTERVAL_END, CameraType.FLOW_SPEED) },
        )
    }

    /** Only the explicit 10019/39 arrival contract is confirmed by the public CP source. */
    fun lifecycle(previous: NavigationState?, extras: Map<String, Any?>): NavigationState? {
        if (previous == null || integer(extras["KEY_TYPE"]) != 10019 ||
            integer(extras["EXTRA_STATE"]) != 39) return previous
        return previous.copy(
            navigationMode = NavigationMode.ARRIVED, routePlanned = false, routeMatched = false,
            navAssistControlAllowed = false, navAssistSourceStatus = "arrived",
            maneuver = NavigationManeuver.DESTINATION, nextTurnType = null, nextTurnDistanceMeters = 0,
            routeRemainDistanceMeters = 0, routeRemainTimeSeconds = 0,
            nextManeuver = NavigationManeuver.NONE, nextManeuverDistanceMeters = null,
            lanes = emptyList(), laneCount = null, lanesPathId = null, lanesObservedAtMs = null,
            autoDisplayLanes = emptyList(), autoDisplayLanesPathId = null,
            acceptedPathId = null, guidancePathId = null, currentStepIndex = null,
            currentLinkIndex = null, currentPointIndex = null, guidanceStepIndex = null,
            guidanceReceivedElapsedMs = null, guidanceCallbackElapsedMs = null,
            guidanceObservedAtMs = null, routeObservedAtMs = null,
            cameras = emptyList(), hasSpeedCameraAhead = false, trafficLight = null,
            routeRecalculating = false,
        )
    }

    private fun integer(raw: Any?): Int? = when (raw) {
        is Byte, is Short, is Int -> (raw as Number).toInt()
        is Long -> raw.takeIf { it in Int.MIN_VALUE.toLong()..Int.MAX_VALUE.toLong() }?.toInt()
        is String -> raw.toIntOrNull()
        else -> null
    }
}
