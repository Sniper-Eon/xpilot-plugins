package com.garan.tesnav.service

import com.garan.tesnav.model.*
import com.google.gson.JsonObject
import java.security.MessageDigest

/** SDK observations only: source clocks survive HTTP polls; C3 retains execution authority.
 * HD lane indices/arrows/geometry are deliberately withheld until their bases are verified.
 */
internal class TencentProbeDecoder(private val androidUserId: Int = 0) {
    private var sdkSession: String? = null
    private var restartLatched = false
    private var routeKey: String? = null
    private var routeRevision = 0L
    private var step = 0
    private var lastSequence = -1L
    private var lastDistance: Int? = null
    private var lastManeuver = NavigationManeuver.UNKNOWN
    private var lastRoad: String? = null
    private var lastGuidanceMono: Long? = null

    @Synchronized fun reset() {
        sdkSession=null;restartLatched=false;routeKey=null;lastSequence=-1;lastGuidanceMono=null
        lastDistance=null;lastManeuver=NavigationManeuver.UNKNOWN;lastRoad=null;step=0
    }
    private fun idle(reason: String) = NavigationState(navigationProvider=NavigationDataSource.TENCENT_API.name,
        navAssistSourceStatus=reason,errorMessage=when(reason) {
            "tencentRestarted" -> "腾讯导航已重启，请重新选择腾讯来源"
            "tencentDisconnected" -> "等待腾讯导航连接"
            else -> "等待腾讯真实导航与有效定位"
        })
    @Synchronized fun decode(raw: JsonObject, mono: Long, wall: Long): NavigationState = try {
        decodeFrame(raw,mono,wall)
    } catch (_: Exception) { idle("tencentInvalid") }

    private fun decodeFrame(raw: JsonObject, mono: Long, wall: Long): NavigationState {
        require(raw.int("schemaVersion")==1 && raw.text("messageType")=="tencent_legacy_observations")
        if(raw.int("androidUserId")!=androidUserId)return idle("tencentWrongUser")
        val session=raw.text("sourceSessionId")?.takeIf{it.length in 1..64} ?: return idle("tencentInvalid")
        if(sdkSession!=null && sdkSession!=session)restartLatched=true
        if(restartLatched)return idle("tencentRestarted")
        sdkSession=session
        val sequence=raw.long("sequence") ?: return idle("tencentInvalid")
        if(sequence<lastSequence)return idle("tencentReordered")
        lastSequence=sequence
        val context=raw.obj("engineContext") ?: return idle("tencentModeUnknown")
        if(!fresh(context.long("sampledMonoMs"),mono,1500))return idle("tencentContextStale")
        val route=raw.text("routeId")?.takeIf{it.isNotEmpty() && it.length<=128} ?: return idle("tencentNoRoute")
        if(raw.bool("released")!=false || context.text("routeId")!=route || context.bool("isStartNav")!=true)
            return idle("tencentNoRoute")
        val mode=context.text("navigationMode")
        if(mode=="simulation" || context.bool("isSimulate")==true)
            return idle("tencentSimulation").copy(navigationMode=NavigationMode.SIMULATION)
        if(mode!="realtime" || context.bool("isRealNav")!=true || context.bool("isSimulate")!=false)
            return idle("tencentModeUnknown")
        val events=raw.obj("events") ?: return idle("tencentGuidanceMissing")
        val distanceEvent=events.obj("LeftDistance") ?: return idle("tencentGuidanceMissing")
        val directionEvent=events.obj("Direction") ?: return idle("tencentGuidanceMissing")
        val guideMono=distanceEvent.long("observedMonoMs") ?: return idle("tencentGuidanceMissing")
        val guideWall=distanceEvent.long("observedWallMs") ?: return idle("tencentGuidanceMissing")
        if(guideMono>mono || guideWall>wall || guideMono<0 || guideWall<0 ||
            directionEvent.long("observedMonoMs")?.let{it>guideMono+250 || it<0}!=false ||
            distanceEvent.obj("values")?.bool("inNavigation")!=true ||
            directionEvent.obj("values")?.bool("inNavigation")!=true)return idle("tencentGuidanceUnsettled")
        val distance=distanceEvent.obj("values")?.obj("distance")?.int("leftDistance")?.takeIf{it in 0..100000}
            ?: return idle("tencentGuidanceMissing")
        val code=directionEvent.obj("values")?.obj("direction")?.int("direction")
        val maneuver=tencentManeuver(code)
        val currentRoad=events.obj("NowRoadName")?.obj("values")?.obj("road")?.text("nowRoadName")
        val nextRoad=events.obj("RoadName")?.obj("values")?.obj("road")?.text("roadName")
        val key="$session:$route:${raw.long("routeRevision") ?: return idle("tencentNoRoute")}"
        if(key!=routeKey) {
            routeKey=key;routeRevision++;step=0;lastDistance=null;lastGuidanceMono=null
        }
        if(lastGuidanceMono!=guideMono) {
            if(lastGuidanceMono!=null && (lastManeuver!=maneuver || lastRoad!=nextRoad ||
                lastDistance?.let{distance>it+50}==true))step++
            lastDistance=distance;lastManeuver=maneuver;lastRoad=nextRoad;lastGuidanceMono=guideMono
        }
        val pathId=stablePath(key)
        val observation=raw.obj("location")
        val value=observation?.obj("values")
        val match=value?.obj("match")
        val routeMatch=value?.obj("routeMatch")
        val matched=match?.text("getMainRouteId")==route && value.bool("isMatchResult")==true &&
            fresh(observation.long("observedMonoMs"),mono,3000) && fresh(value.long("timestamp"),wall,3000) &&
            routeMatch?.int("getMatchedIndex")?.let{it>=0}==true &&
            routeMatch.text("getLinkId")?.let{it.matches(Regex("-?[0-9]{1,20}")) && it.trimStart('-','0').isNotEmpty()}==true
        val fix=value?.obj("originalFix")
        val fixWall=fix?.long("timestamp")
        val received=observation?.long("observedMonoMs")
        val fixValid=matched && fresh(received,mono,3000) && fresh(fixWall,wall,3000) &&
            fix?.int("coordinateType")==1 && fix.int("status")==2 && fix.int("rssi")?.let{it>=2}==true &&
            fix.double("accuracy")?.let{it.isFinite() && it>0 && it<=200}==true &&
            fix.double("latitude")?.let{it.isFinite() && it in -90.0..90.0}==true &&
            fix.double("longitude")?.let{it.isFinite() && it in -180.0..180.0}==true &&
            fix.double("direction")?.let{it.isFinite() && it>=0 && it<360}==true
        val speedEvent=events.obj("Speed")
        val speed=speedEvent?.obj("values")?.obj("speed")?.double("speed")
            ?.takeIf{it.isFinite() && it in 0.0..300.0 && fresh(speedEvent.long("observedMonoMs"),mono,3000)}
        return NavigationState(navigationProvider=NavigationDataSource.TENCENT_API.name,
            navigationMode=NavigationMode.REALTIME,routePlanned=true,
            latitude=fix?.double("latitude").takeIf{fixValid},longitude=fix?.double("longitude").takeIf{fixValid},
            accuracy=fix?.double("accuracy")?.toFloat().takeIf{fixValid},bearing=fix?.double("direction")?.toFloat().takeIf{fixValid},
            locationTime=fixWall.takeIf{fixValid},locationObservedAtMs=fixWall.takeIf{fixValid},
            locationReceivedElapsedMs=received.takeIf{fixValid},locationSourceStatus=if(fixValid)"tencent-phone-original" else "unqualified",
            speedKph=speed?.toFloat() ?: 0f,gpsSignalWeak=!fixValid || speed==null,routeMatched=matched,
            currentRoad=currentRoad?.take(256),nextRoad=nextRoad?.take(256),nextTurnType=code,nextTurnDistanceMeters=distance,
            maneuver=maneuver,acceptedPathId=pathId,guidancePathId=pathId,currentStepIndex=step,guidanceStepIndex=step,
            guidanceObservedAtMs=guideWall,guidanceReceivedElapsedMs=guideMono,guidanceCallbackElapsedMs=guideMono,
            routeObservedAtMs=guideWall,routeRevision=routeRevision,navAssistControlAllowed=false,
            navAssistSourceStatus=if(fixValid)"tencentPending" else "tencentPositionUnqualified")
    }
    private fun stablePath(key: String): Long {
        val digest=MessageDigest.getInstance("SHA-256").digest(key.toByteArray(Charsets.UTF_8))
        var value=0L;for(i in 0..7)value=(value shl 8) or (digest[i].toLong() and 255)
        return (value and Long.MAX_VALUE).coerceAtLeast(1)
    }
    private fun fresh(stamp: Long?,now: Long,budget: Long)=stamp!=null && stamp>=0 && stamp<=now && now-stamp<=budget
}

private fun JsonObject?.obj(key:String):JsonObject?=this?.get(key)?.takeIf{it.isJsonObject}?.asJsonObject
private fun JsonObject?.text(key:String):String?=this?.get(key)?.takeIf{it.isJsonPrimitive}?.asString
private fun JsonObject?.long(key:String):Long?=text(key)?.toLongOrNull()
private fun JsonObject?.int(key:String):Int?=text(key)?.toIntOrNull()
private fun JsonObject?.double(key:String):Double?=text(key)?.toDoubleOrNull()
private fun JsonObject?.bool(key:String):Boolean?=text(key)?.toBooleanStrictOrNull()

/** Old hosts expose a separate turn-only linkage. An unhealthy Tencent source
 * must remove that linkage too; routeActive=false alone is insufficient there.
 */
internal fun tencentWireState(state: NavigationState): NavigationState =
    if(state.navAssistControlAllowed) state else state.copy(
        navigationMode=NavigationMode.IDLE,routePlanned=false,routeMatched=false,
        latitude=null,longitude=null,accuracy=null,bearing=null,
        locationObservedAtMs=null,locationReceivedElapsedMs=null,guidanceObservedAtMs=null,
        guidanceReceivedElapsedMs=null,guidanceCallbackElapsedMs=null,
        lanes=emptyList(),laneCount=null,lanesObservedAtMs=null,lanesPathId=null)

/** Existing independent Android GNSS, after its verified WGS84 -> GCJ02 conversion.
 * This can replace position, never manufacture route matching or renew guidance.
 */
internal fun tencentWithPhoneFix(state: NavigationState, fix: NavigationLocationObservation?, mono: Long, wall: Long): NavigationState {
    if(state.navigationMode!=NavigationMode.REALTIME || !state.routePlanned || state.routeMatched!=true ||
        fix==null || fix.observationTimeOnly || independentPlanningOrigin(fix,mono,wall)==null ||
        fix.accuracyM?.let{it<=25}!=true ||
        fix.speedMps?.let{it.isFinite() && it in 0.0..83.333333}!=true ||
        fix.bearingDeg?.let{it.isFinite() && it>=0 && it<360}!=true)return state
    return state.copy(latitude=fix.latitude,longitude=fix.longitude,accuracy=fix.accuracyM.toFloat(),
        bearing=fix.bearingDeg.toFloat(),speedKph=(fix.speedMps*3.6).toFloat(),locationTime=fix.measuredAtMs,
        locationObservedAtMs=fix.measuredAtMs,locationReceivedElapsedMs=fix.receivedElapsedMs,
        locationSourceStatus="phone-gps",gpsSignalWeak=false)
}
