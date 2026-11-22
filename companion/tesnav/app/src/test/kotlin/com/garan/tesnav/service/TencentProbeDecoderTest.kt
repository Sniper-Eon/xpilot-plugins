package com.garan.tesnav.service

import com.garan.tesnav.model.*
import com.garan.tesnav.export.NavAssistV2Mapper
import com.google.gson.JsonParser
import org.junit.Assert.*
import org.junit.Test

class TencentProbeDecoderTest {
    private fun frame() = JsonParser.parseString("""{
      "schemaVersion":1,"messageType":"tencent_legacy_observations","androidUserId":0,"sourceProfile":"tc-v61-legacy-v7",
      "sourceSessionId":"sdk-one","sequence":10,"routeId":"route-A","routeRevision":1,"released":false,
      "engineContext":{"navigationMode":"realtime","routeId":"route-A","isRealNav":true,
        "isStartNav":true,"isSimulate":false,"sampledMonoMs":1000},
      "events":{
        "LeftDistance":{"observedWallMs":10000,"observedMonoMs":1000,
          "values":{"inNavigation":true,"distance":{"leftDistance":45}}},
        "Direction":{"observedWallMs":9999,"observedMonoMs":999,
          "values":{"inNavigation":true,"direction":{"direction":3}}},
        "NowRoadName":{"observedWallMs":9998,"observedMonoMs":998,
          "values":{"inNavigation":true,"road":{"nowRoadName":"甲路","roadName":"甲路"}}},
        "RoadName":{"observedWallMs":9999,"observedMonoMs":999,
          "values":{"inNavigation":true,"road":{"nowRoadName":"甲路","roadName":"乙路"}}},
        "Speed":{"observedWallMs":10000,"observedMonoMs":1000,"values":{"speed":{"speed":0}}}},
      "location":{"observedWallMs":10000,"observedMonoMs":1000,"values":{
        "status":2,"rssi":3,"timestamp":9950,"isMatchResult":true,
        "match":{"getMainRouteId":"route-A"},"routeMatch":{"getMatchedIndex":0,"getLinkId":"123"},
        "originalFix":{"latitude":23.1,"longitude":113.1,"accuracy":5.0,"direction":90,
          "coordinateType":1,"timestamp":9950,"status":2,"rssi":3,"provider":"gps"}}},
      "hd":{"values":{"lane":{"getCurLaneNum":0,"getLaneMatchedIndex":-1}}},"controlUsable":false
    }""").asJsonObject
    private fun state(raw: com.google.gson.JsonObject = frame()) = TencentProbeDecoder().decode(raw,1100,10100)

    @Test fun `source is selectable and never borrows Amap data`() {
        assertTrue(NavigationSourcePolicy.canSelect(NavigationDataSource.TENCENT_API,true))
        val amap=NavigationState(routePlanned=true,nextRoad="高德旧路")
        val selected=NavigationSourcePolicy.stateFor(NavigationDataSource.TENCENT_API,amap,null)
        assertFalse(selected.routePlanned)
        assertNull(selected.nextRoad)
    }
    @Test fun `Tencent common maneuvers use SDK constants including codes different from Amap`() {
        for((code,expected) in mapOf(1 to NavigationManeuver.STRAIGHT,2 to NavigationManeuver.TURN_LEFT,
            3 to NavigationManeuver.TURN_RIGHT,4 to NavigationManeuver.U_TURN_LEFT,
            10 to NavigationManeuver.SLIGHT_LEFT,20 to NavigationManeuver.SLIGHT_RIGHT,
            12 to NavigationManeuver.KEEP_LEFT,22 to NavigationManeuver.KEEP_RIGHT,
            30 to NavigationManeuver.SHARP_LEFT,40 to NavigationManeuver.SHARP_RIGHT,
            87 to NavigationManeuver.U_TURN_RIGHT,60 to NavigationManeuver.DESTINATION)) {
            val f=frame();f.getAsJsonObject("events").getAsJsonObject("Direction").getAsJsonObject("values")
                .getAsJsonObject("direction").addProperty("direction",code)
            assertEquals("Tencent code $code",expected,state(f).maneuver)
        }
    }
    @Test fun `qualified raw observations map directions and original clocks without granting authority`() {
        val s=state()
        assertEquals(NavigationMode.REALTIME,s.navigationMode)
        assertEquals(NavigationManeuver.TURN_RIGHT,s.maneuver)
        assertEquals(45,s.nextTurnDistanceMeters)
        assertEquals(9950L,s.locationObservedAtMs)
        assertEquals(1000L,s.locationReceivedElapsedMs)
        assertEquals(10000L,s.guidanceObservedAtMs)
        assertFalse(s.navAssistControlAllowed)
        assertTrue(s.routeMatched==true)
        assertTrue(s.lanes.isEmpty());assertNull(s.laneCount)
        val gate=NavigationSourceGate(3000,6000).also{it.arm(900)}
        val ready=gate.prepare(s,1100,10100)
        assertTrue(gate.reason,ready.navAssistControlAllowed)
        val wire=NavAssistV2Mapper.snapshot(ready,"test",1,10100,1200)
        assertTrue(wire.routeActive);assertEquals("turn_right",wire.guidance?.maneuver)
    }
    @Test fun `repeated HTTP reads do not renew observations or mint new route events`() {
        val d=TencentProbeDecoder();val f=frame();val first=d.decode(f,1100,10100)
        val again=d.decode(f,1500,10500)
        assertEquals(first.guidanceObservedAtMs,again.guidanceObservedAtMs)
        assertEquals(first.currentStepIndex,again.currentStepIndex)
        assertEquals(first.acceptedPathId,again.acceptedPathId)
        val stale=d.decode(f,5001,14001)
        assertFalse(NavigationSourceGate(3000,6000).also{it.arm(900)}.prepare(stale,5001,14001).navAssistControlAllowed)
    }
    @Test fun `simulation release missing mode and cross route never authorize driving`() {
        for(kind in listOf("simulation","unknown","mismatch","released","missing")) {
            val f=frame();val c=f.getAsJsonObject("engineContext")
            when(kind) {
                "simulation"->{c.addProperty("navigationMode","simulation");c.addProperty("isSimulate",true)}
                "unknown"->c.addProperty("navigationMode","unknown")
                "mismatch"->c.addProperty("routeId","old-route")
                "released"->f.addProperty("released",true)
                "missing"->f.remove("engineContext")
            }
            val s=state(f);val gate=NavigationSourceGate(3000,6000).also{it.arm(900)}
            assertFalse(kind,gate.prepare(s,1100,10100).navAssistControlAllowed)
        }
    }
    @Test fun `zero accuracy unknown coordinates and old or future fixes are withheld`() {
        for(kind in listOf("accuracy","coord","old","future","unmatched","context-old")) {
            val f=frame();val loc=f.getAsJsonObject("location").getAsJsonObject("values")
            val fix=loc.getAsJsonObject("originalFix")
            when(kind) {
                "accuracy"->fix.addProperty("accuracy",0)
                "coord"->fix.addProperty("coordinateType",-1)
                "old"->fix.addProperty("timestamp",6000)
                "future"->fix.addProperty("timestamp",11000)
                "unmatched"->loc.getAsJsonObject("routeMatch").addProperty("getMatchedIndex",-1)
                "context-old"->f.getAsJsonObject("engineContext").addProperty("sampledMonoMs",-1)
            }
            val s=state(f);val gate=NavigationSourceGate(3000,6000).also{it.arm(900)}
            assertFalse(kind,gate.prepare(s,1100,10100).navAssistControlAllowed)
        }
    }
    @Test fun `SDK process restart is latched until an explicit source reset`() {
        val d=TencentProbeDecoder();d.decode(frame(),1100,10100)
        val f=frame().apply{addProperty("sourceSessionId","sdk-two")}
        assertFalse(d.decode(f,1100,10100).routePlanned)
        assertFalse(d.decode(f,1200,10200).routePlanned)
        d.reset();assertTrue(d.decode(f,1200,10200).routePlanned)
    }
    @Test fun `unknown Tencent turn codes stay unknown and never use Amap code tables`() {
        val f=frame();f.getAsJsonObject("events").getAsJsonObject("Direction").getAsJsonObject("values")
            .getAsJsonObject("direction").addProperty("direction",999)
        assertEquals(NavigationManeuver.UNKNOWN,state(f).maneuver)
        assertEquals(0L,NavAssistV2Mapper.snapshot(state(f),"test",1,10100,1200).maneuverEventId)
    }
    @Test fun `failed source gate withdraws the entire wire input including turn only linkage`() {
        val unqualified=state().copy(navAssistControlAllowed=false)
        val wire=NavAssistV2Mapper.snapshot(tencentWireState(unqualified),"test",1,10100,1200)
        assertFalse(wire.routeActive);assertEquals("idle",wire.navigationMode)
        assertNull(wire.location);assertNull(wire.guidance);assertEquals(0L,wire.maneuverEventId)
        val admitted=unqualified.copy(navAssistControlAllowed=true)
        assertEquals(admitted,tencentWireState(admitted))
    }
    @Test fun `qualified independent phone GPS is preferred without refreshing Tencent guidance`() {
        val original=state()
        val fix=NavigationLocationObservation("phone-gps",10050,1050,0,23.2,113.2,3.0,5.0,100.0,
            NavigationCoordinateSystem.GCJ02,true)
        val fused=tencentWithPhoneFix(original,fix,1100,10100)
        assertEquals(23.2,fused.latitude!!,0.0);assertEquals("phone-gps",fused.locationSourceStatus)
        assertEquals(10050L,fused.locationObservedAtMs);assertEquals(1050L,fused.locationReceivedElapsedMs)
        assertEquals(original.guidanceObservedAtMs,fused.guidanceObservedAtMs)
        assertEquals(original.guidanceReceivedElapsedMs,fused.guidanceReceivedElapsedMs)
        assertEquals(18f,fused.speedKph)
        assertEquals(original,tencentWithPhoneFix(original,fix.copy(measuredAtMs=6000),1100,10100))
        val unmatched=original.copy(routeMatched=false)
        assertEquals(unmatched,tencentWithPhoneFix(unmatched,fix,1100,10100))
        assertEquals(original,tencentWithPhoneFix(original,fix.copy(observationTimeOnly=true),1100,10100))
    }
    @Test fun `new phone fix cannot conceal stale Tencent route matching`() {
        val f=frame();f.getAsJsonObject("location").getAsJsonObject("values").addProperty("timestamp",100)
        assertFalse(state(f).routeMatched==true)
    }
    @Test fun `another Android user or clone cannot supply navigation observations`() {
        val clone=frame().apply{addProperty("androidUserId",900)}
        assertFalse(state(clone).routePlanned)
        val missing=frame().apply{remove("androidUserId")}
        assertFalse(state(missing).routePlanned)
    }
}
