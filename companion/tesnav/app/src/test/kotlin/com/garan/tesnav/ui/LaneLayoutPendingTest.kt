package com.garan.tesnav.ui

import com.garan.tesnav.model.*
import org.junit.Assert.*
import org.junit.Test

/** Failure: a held old index highlights an arrow in the upcoming wider layout;
 * the current UI ignores the existing pending-layout reason in C3 feedback.
 */
class LaneLayoutPendingTest {
    private fun oem(count:Int?)=OemVehicleLaneState(receivedAtMs=1,
        c3LanePosition=C3LanePosition(true,2,count,"roadLayoutPending","commaGeo"))
    @Test fun pendingOldIndexNeverHighlightsAFutureLayoutArrow() {
        val state=NavigationState(navigationMode=NavigationMode.REALTIME,
            navAssistSourceStatus="healthy",routePlanned=true,routeMatched=true,
            acceptedPathId=42,guidancePathId=42,lanesPathId=42,
            lanes=(0..4).map { LaneState(it,listOf(LaneAction.STRAIGHT),true,0) })
        assertFalse(LaneGuidancePresenter.present(state,oem(4))!!.items.any { it.current })
    }
    @Test fun retainedNumberWithUnknownTotalIsExplicitlyPending() {
        val text=LaneGuidancePresenter.lanePositionText(oem(null))!!
        assertTrue(text.contains("第2条"))
        assertTrue(text.contains("布局待确认"))
        assertTrue(text.contains("总数未知"))
    }
}
