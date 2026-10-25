package com.jixiexiaoge.drivingassist.data

import android.os.SystemClock
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.*
import okio.ByteString

/** X-Pilot native metadata connection. No image subscription or sensor inference. */
class CarrotWsClient(
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default + SupervisorJob())
) {
    companion object { val DEFAULT_SERVICES = listOf("carState") }
    private val client = OkHttpClient.Builder().pingInterval(15, java.util.concurrent.TimeUnit.SECONDS).build()
    private val freshness = FreshTelemetry()
    private var socket: WebSocket? = null
    private var timer: Job? = null
    private var retry: Job? = null
    @Volatile private var generation = 0L
    @Volatile private var wantedHost: String? = null
    private var attempts = 0
    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState = _connectionState.asStateFlow()
    private val _isDataTimeout = MutableStateFlow(true)
    val isDataTimeout = _isDataTimeout.asStateFlow()
    private val _vehicleData = MutableStateFlow<VehicleData?>(null)
    val vehicleData = _vehicleData.asStateFlow()
    private val _deviceStatus = MutableStateFlow(DeviceStatus())
    val deviceStatus = _deviceStatus.asStateFlow()
    private val _cameraFrame = MutableStateFlow<CameraFrame?>(null)
    val cameraFrame = _cameraFrame.asStateFlow()
    var onCameraFrame: ((CameraFrame) -> Unit)? = null

    @Synchronized fun connect(host: String) {
        val clean = host.trim().removePrefix("http://").removePrefix("https://").substringBefore('/')
        if (clean == wantedHost && _connectionState.value != ConnectionState.DISCONNECTED) return
        disconnect()
        wantedHost = clean
        val token = generation
        _connectionState.value = ConnectionState.CONNECTING
        _isDataTimeout.value = true
        timer = scope.launch {
            while (isActive && token == generation) {
                delay(250)
                synchronized(this@CarrotWsClient) {
                    if (token == generation && freshness.current(SystemClock.elapsedRealtime()) == null) {
                        _vehicleData.value = null
                        _isDataTimeout.value = true
                    }
                }
            }
        }
        socket = client.newWebSocket(Request.Builder().url("ws://$clean:7000/ws/compact_state").build(),
            object : WebSocketListener() {
                override fun onOpen(ws: WebSocket, response: Response) {
                    synchronized(this@CarrotWsClient) {
                        if (token != generation) { ws.close(1000, "superseded"); return }
                        _connectionState.value = ConnectionState.CONNECTED
                    }
                }
                override fun onMessage(ws: WebSocket, bytes: ByteString) {
                    synchronized(this@CarrotWsClient) {
                        if (token != generation) return
                        val now = SystemClock.elapsedRealtime()
                        if (!freshness.accept(bytes.toByteArray(), now)) return
                        val car = freshness.current(now) ?: return
                        attempts = 0
                        _vehicleData.value = VehicleData(carState = car)
                        _isDataTimeout.value = false
                    }
                }
                override fun onClosing(ws: WebSocket, code: Int, reason: String) { ws.close(code, reason) }
                override fun onClosed(ws: WebSocket, code: Int, reason: String) { lost(token) }
                override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) { lost(token) }
            })
    }

    @Synchronized private fun lost(token: Long) {
        if (token != generation || wantedHost == null) return
        freshness.clear()
        _vehicleData.value = null
        _isDataTimeout.value = true
        _connectionState.value = ConnectionState.DISCONNECTED
        retry?.cancel()
        retry = scope.launch {
            delay((2000L shl attempts.coerceAtMost(4)).coerceAtMost(30000L))
            attempts++
            val host = wantedHost
            if (host != null && token == generation) connect(host)
        }
    }

    @Synchronized fun disconnect() {
        generation++
        wantedHost = null
        retry?.cancel()
        timer?.cancel()
        socket?.cancel()
        socket = null
        freshness.clear()
        _vehicleData.value = null
        _isDataTimeout.value = true
        _connectionState.value = ConnectionState.DISCONNECTED
    }

    // Kept for upstream UI API compatibility. This variant never requests camera frames.
    fun connectCamera(host: String) = Unit
    fun resetReconnectAttempts() { attempts = 0 }
}

data class VehicleData(
    val carState: CarState? = null,
    val modelV2: ModelV2? = null,
    val controlsState: ControlsState? = null,
    val selfdriveState: SelfdriveState? = null,
    val carrotMan: Map<String, Any?>? = null,
    val gpsLocation: GpsLocation? = null,
    val timestamp: Long = System.currentTimeMillis()
)

data class CarState(
    val vEgo: Float = 0f,           // m/s
    val steeringAngleDeg: Float = 0f,
    val leftLatDist: Float = 0f,    // 横向距离 (m)
    val leftBlindspot: Boolean = false,  // 左盲区
    val rightBlindspot: Boolean = false, // 右盲区
    val leftBlinker: Boolean = false,
    val rightBlinker: Boolean = false,
)

data class ModelV2(
    val leadX: Float = 0f,          // 前车距离 m
    val leadV: Float = 0f,          // 前车速度 m/s
    val leadProb: Float = 0f,       // 前车置信度
    val laneLineProbs: List<Float> = emptyList(),  // 4条车道线概率
    val leftDist: Float = 0f,       // 到左路缘距离 (m)
    val rightDist: Float = 0f,      // 到右路缘距离 (m)
)

data class ControlsState(
    val enabled: Boolean = false,
    val active: Boolean = false,
    val vCruise: Float = 0f,        // 巡航设定 m/s
    val angleSteers: Float = 0f,    // 目标方向盘角
)

data class SelfdriveState(
    val enabled: Boolean = false,
    val active: Boolean = false,
    val engageAllowed: Boolean = false,
)

data class GpsLocation(
    val latitude: Double = 0.0,
    val longitude: Double = 0.0,
    val speed: Float = 0f,
    val bearing: Float = 0f,
    val accuracy: Float = 0f,
)

data class DeviceStatus(
    val cpuTemp: Float = 0f,
    val cpuUsage: Float = 0f,
    val memoryUsage: Float = 0f,
    val batteryPercent: Int = 0,
    val networkType: String = "",
    val gpsLatitude: Double = 0.0,
    val gpsLongitude: Double = 0.0,
)

data class CameraFrame(
    val camera: String,
    val codec: String,
    val frameId: Int,
    val width: Int,
    val height: Int,
    val keyFrame: Boolean,
    val payload: ByteArray,
    val timestamp: Long
)

enum class ConnectionState {
    DISCONNECTED, CONNECTING, CONNECTED
}

