import com.jixiexiaoge.drivingassist.navigation.*
import com.jixiexiaoge.drivingassist.data.CompactStateDecoder
import com.jixiexiaoge.drivingassist.AmapManeuver
import com.jixiexiaoge.drivingassist.AmapIconSource
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.File
import java.util.Base64
import kotlin.system.exitProcess

fun main(args: Array<String>) = runBlocking {
 if (args[0] == "decode") {
  val frames = CompactStateDecoder.decode(Base64.getDecoder().decode(args[1]))
  println(JSONObject(mapOf("decoded" to frames.map { mapOf("service" to it.service, "values" to it.values) })))
  return@runBlocking
 }
 val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
 val client = NaviWebSocketV2Client(scope)
 client.setTarget("127.0.0.1", args[1].toInt()); client.start()
 try {
  withTimeout(15_000) { while (!client.isReady()) delay(20) }
  val stamp=System.currentTimeMillis()
  val kind=args[0]
  val icon=when(kind) { "sharp" -> 6; "exit" -> 25; else -> 3 }
  val guide=GuidanceData(80,AmapManeuver.toCarrotTurnType(icon,if(kind=="exit") AmapIconSource.MOBILE_SDK else AmapIconSource.AUTO_BROADCAST),roadName="synthetic-road").toJson()
  val values=mapOf(
   "vehicle" to VehicleData(23.0,113.0,speedKph=54.0,virtualGps=false).toJson(),
   "navigation_status" to NavigationStatusData("guiding",true,false,true).toJson(),
   "route" to JSONObject(mapOf("remain_distance_m" to 10000, "remain_time_sec" to 900, "total_distance_m" to 12000)),
   "guidance_current" to guide,
   "lane_current" to (if(kind=="model") LaneData(laneCount=5,currentLane=2,laneSource="model",modelCount=5,modelCurrentLane=2)
    else LaneData(laneCount=3, lanes=(0..2).map { LaneItem(index=it,direction="0",isRecommended=it==2) },roadCategory=6)).toJson()
  )
  for ((name,value) in values) check(client.sendJsonData(name,true,value,sourceTimestampMs=stamp))
  println(JSONObject(mapOf("ready" to true,"streams" to client.getSession()!!.streams.size,"turn_type" to guide.getInt("turn_type"))))
  readLine()
 } finally { client.stop();scope.cancel() }
 exitProcess(0)
}
