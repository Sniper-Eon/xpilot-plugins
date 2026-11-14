package com.garan.tesnav.vision

import android.app.*
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import android.util.Base64
import com.google.gson.Gson
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.MediaType.Companion.toMediaType
import java.util.concurrent.TimeUnit

internal data class PhoneCameraFrame(val version: Int, val request_id: String, val stream_id: String, val frame_id: Long,
    val capture_mono_ns: Long, val width: Int, val height: Int, val jpeg_b64: String,
    val ego_speed_mps: Double?, val ground_inverse: List<Double>?, val roi: Map<String, List<List<Double>>>, val capture_age_ms: Double? = null,
    val bridge_wait_ms: Double? = null, val bridge_processing_ms: Double? = null, val jpeg_bytes: Long? = null)

class PhoneVisionService : Service() {
    companion object {
        private const val OCCUPIED_THRESHOLD = 0.5f
        /** side_vehicle320 is the heavy model; blind-spot still runs on every accepted frame. */
        private const val SIDE_DETECT_PERIOD_MS = 250L
        val status = MutableStateFlow("尚未启动")
    }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null
    @Volatile private var lastTimingReport: Map<String, Any> = emptyMap()
    private var cpuThreads = 2
    private var targetFps = 8
    private var minimumIdleMs = 0L
    private var prefetchEnabled = true
    private var vasmDetector: VasmDetector? = null
    @Volatile private var vasmStatus: String = "未运行"
    private var sideDetector: PhoneVehicleDetector? = null
    @Volatile private var sideStatus: String = "未运行"
    override fun dump(fd: java.io.FileDescriptor, writer: java.io.PrintWriter, args: Array<out String>) {
        writer.println("VISION_TIMINGS " + Gson().toJson(lastTimingReport))
    }
    private val availability = VisionAvailability { status.value = it }

    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") { availability.unavailable("已停止"); stopSelf(); return START_NOT_STICKY }
        if (job?.isActive == true) return START_STICKY
        cpuThreads = (intent?.getIntExtra("cpu_threads", 2) ?: 2).coerceIn(1, 4)
        targetFps = (intent?.getIntExtra("target_fps", 8) ?: 8).coerceIn(1, 8)
        minimumIdleMs = (intent?.getIntExtra("minimum_idle_ms", 0) ?: 0).coerceIn(0, 50).toLong()
        prefetchEnabled = intent?.getBooleanExtra("prefetch_enabled", true) ?: true
        availability.unavailable("正在连接")
        val settings = getSharedPreferences("phone_vision", MODE_PRIVATE)
        val host = settings.getString("host", "")!!.trim()
        val token = settings.getString("token", "")!!.trim()
        if (host.isBlank() || token.length < 32) { availability.unavailable("请填写 C3 地址和连接码"); stopSelf(); return START_NOT_STICKY }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("phone_vision", "侧方车辆识别", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, PhoneVisionActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, PhoneVisionService::class.java).setAction("stop"), PendingIntent.FLAG_IMMUTABLE)
        startForeground(8767, Notification.Builder(this, "phone_vision").setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle("特会开 · 手机视觉运行中").setContentText("侧方车辆识别").setContentIntent(open)
            .addAction(Notification.Action.Builder(null, "停止", stop).build()).build())
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TesNav:PhoneVision")
            .apply { acquire(10 * 60 * 1000L) }
        scope.launch {
            var renewAt=SystemClock.elapsedRealtime()+5*60*1000L
            while (isActive) {
                delay(250)
                availability.expire(SystemClock.elapsedRealtime())
                if (SystemClock.elapsedRealtime() >= renewAt) {
                    wakeLock?.let { if (it.isHeld) it.release(); it.acquire(10*60*1000L) }
                    renewAt=SystemClock.elapsedRealtime()+5*60*1000L
                }
            }
        }
        job = scope.launch {
            try {
                runVision(host, token)
            }
            catch (e: Exception) { availability.unavailable(e.message ?: e.javaClass.simpleName) }
            finally { stopSelf() }
        }
        return START_STICKY
    }

    private data class DownloadedFrame(val frame: PhoneCameraFrame, val host: String, val endpoint: String,
        val requestStartedMs: Long, val downloadedMs: Long)

    private suspend fun runVision(host: String, token: String) = coroutineScope {
        require(host.matches(Regex("[A-Za-z0-9.-]+(?::[0-9]{1,5})?"))) { "C3 地址格式不正确" }
        val preferences = getSharedPreferences("phone_vision", MODE_PRIVATE)
        val client = OkHttpClient.Builder().connectTimeout(2, TimeUnit.SECONDS).readTimeout(2, TimeUnit.SECONDS)
            .callTimeout(3, TimeUnit.SECONDS).build()
        val gson = Gson()
        val fetchAttempts = java.util.concurrent.atomic.AtomicLong()
        val fetchFrame: suspend () -> DownloadedFrame = {
            fetchAttempts.incrementAndGet()
            val started = SystemClock.elapsedRealtime()
            val currentHost = PhoneVisionC3Address.navigationHost ?: host
            val endpoint = "http://" + currentHost + if (':' in currentHost) "" else ":8767"
            val request = Request.Builder().url("$endpoint/v1/frame").header("Authorization", "Bearer $token").header("X-Phone-Vision-Encoding", "gzip-v1").build()
            val frame = client.newCall(request).execute().use { response ->
                check(response.isSuccessful) { if (response.code == 503) "等待 C3 相机启动" else "C3 连接失败（${response.code}）" }
                val source = response.body ?: error("画面为空")
                gson.fromJson(readVisionJsonBody(source, 1_500_000), PhoneCameraFrame::class.java)
            }
            check(frame.version == 1 && frame.width in 320..1928 && frame.height in 200..1208) { "画面格式不兼容" }
            DownloadedFrame(frame, currentHost, endpoint, started, SystemClock.elapsedRealtime())
        }
        val prefetched = if (prefetchEnabled) LatestVisionFrames(this, 1000L / targetFps, fetchFrame,
            { e ->
                availability.unavailable(e.message ?: "等待 C3 画面")
                lastTimingReport = mapOf("outcome" to "fetch_error", "error_type" to e.javaClass.simpleName,
                    "fetch_attempts" to fetchAttempts.get(), "report_elapsed_ms" to SystemClock.elapsedRealtime())
            }, SystemClock::elapsedRealtime) else null
        val cpLane = CpLaneDetector(this@PhoneVisionService)
        try {
            availability.unavailable("正在加载手机视觉模型")
            run {
                try {
                    sideDetector = PhoneVehicleDetector(this@PhoneVisionService, cpuThreads)
                    sideStatus = "运行中"
                } catch (e: Exception) {
                    sideStatus = "测速模型不可用"
                    android.util.Log.w("PhoneVisionSide", "side vehicle model failed", e)
                }
                var tracker = SideVehicleTracker()
                var lastSideDetectMs = 0L
                val held = HashMap<String, Pair<Long, SideObservation>>()
                fun clearMotion() {
                    tracker = SideVehicleTracker()
                    held.clear()
                    lastSideDetectMs = 0L
                }
                fun publish(side: String, fresh: Map<String, SideObservation?>?, captureNs: Long): Map<String, Any>? {
                    if (fresh != null) {
                        val observation = fresh[side]
                        if (observation == null) {
                            held.remove(side)
                            return null
                        }
                        val wire = measurementFields(observation, 0)
                        if (wire == null) held.remove(side) else held[side] = captureNs to observation
                        return wire
                    }
                    val cached = held[side] ?: return null
                    val age = (captureNs - cached.first) / 1_000_000
                    if (age > Int.MAX_VALUE) {
                        held.remove(side)
                        return null
                    }
                    val wire = measurementFields(cached.second, age.toInt())
                    if (wire == null) held.remove(side)
                    return wire
                }
                var lastCapture = -1L
                var streamId: String? = null
                var activeHost: String? = null
                var attempts = 0L; var accepted = 0L; var expired = 0L; var duplicates = 0L
                while (currentCoroutineContext().isActive) {
                    val start = SystemClock.elapsedRealtime()
                    var requestStarted = start
                    attempts++
                    val timings = linkedMapOf<String, Any>("attempt" to attempts, "cpu_threads" to cpuThreads,
                        "target_fps" to targetFps, "prefetch" to prefetchEnabled, "minimum_idle_ms" to minimumIdleMs)
                    try {
                        val packet = prefetched?.next() ?: fetchFrame()
                        currentCoroutineContext().ensureActive()
                        requestStarted = packet.requestStartedMs
                        val frame = packet.frame
                        timings["download_ms"] = packet.downloadedMs-packet.requestStartedMs
                        timings["queue_wait_ms"] = maxOf(0L, SystemClock.elapsedRealtime()-packet.downloadedMs)
                        timings["frame_id"] = frame.frame_id
                        timings["capture_age_ms"] = frame.capture_age_ms ?: -1
                        timings["server_wait_ms"] = frame.bridge_wait_ms ?: -1
                        timings["bridge_processing_ms"] = frame.bridge_processing_ms ?: -1
                        timings["jpeg_bytes"] = frame.jpeg_bytes ?: -1
                        // A frame from the previous host must never be posted to the new C3.
                        if (packet.host != (PhoneVisionC3Address.navigationHost ?: host)) throw ExpiredVisionFrame()
                        if (packet.host != activeHost) {
                                activeHost = packet.host; clearMotion(); lastCapture = -1L; streamId = null
                            preferences.edit().putString("host", packet.host).apply()
                        }
                        if (streamId != frame.stream_id) {
                                streamId = frame.stream_id; lastCapture = -1L; clearMotion()
                        }
                        if (frame.capture_mono_ns <= lastCapture) {
                            duplicates++; timings["outcome"]="duplicate"; delay(80); continue
                        }
                        lastCapture = frame.capture_mono_ns
                        if (!PhoneVisionBudget.canSubmit(frame.capture_age_ms, SystemClock.elapsedRealtime()-requestStarted, frame.bridge_wait_ms)) throw ExpiredVisionFrame()
                        val beforeDecode = SystemClock.elapsedRealtime()
                        val encoded = Base64.decode(frame.jpeg_b64, Base64.DEFAULT)
                        // inScaled would resize away from the calibrated frame, and a hardware
                        // bitmap cannot be sampled. Both detectors share this software copy.
                        val options = BitmapFactory.Options().apply {
                            inPreferredConfig = Bitmap.Config.ARGB_8888
                            inScaled = false
                        }
                        var bitmap = BitmapFactory.decodeByteArray(encoded, 0, encoded.size, options) ?: error("画面解码失败")
                        if (bitmap.config != Bitmap.Config.ARGB_8888) {
                            val software = bitmap.copy(Bitmap.Config.ARGB_8888, false)
                            bitmap.recycle()
                            bitmap = software ?: error("画面解码失败")
                        }
                        timings["jpeg_decode_ms"] = SystemClock.elapsedRealtime()-beforeDecode
                        val beforeDetect = SystemClock.elapsedRealtime()
                        var laneCandidate: CpLaneResult? = null
                        val laneEnabled=preferences.getBoolean("cp_lane_enabled",true)
                        var sideDetections: List<SideDetection>? = null
                        val vasm = try {
                            check(bitmap.width == frame.width && bitmap.height == frame.height) { "图像尺寸不一致" }
                            val meanLuma=VisionModels.meanLuma(bitmap)
                            val laneModel=VisionModels.select(preferences, meanLuma)
                            if (laneEnabled) {
                                val laneStart = SystemClock.elapsedRealtime()
                                // 恢复 v39 行为：带路面掩码推理。删除彩色路面功能后这里被改成 false，
                                // 而原生引擎的车道头依赖同一条推理路径，会退化成「第 0 类（不可用）」。
                                laneCandidate = cpLane.detect(bitmap, laneModel, roadEnabled=true)
                                timings["lane_model_ms"] = SystemClock.elapsedRealtime()-laneStart
                            } else cpLane.close()
                            val nowMs = SystemClock.elapsedRealtime()
                            if (nowMs - lastSideDetectMs >= SIDE_DETECT_PERIOD_MS) {
                                lastSideDetectMs = nowMs
                                val started = SystemClock.elapsedRealtime()
                                sideDetections = try {
                                    val detector = sideDetector
                                    if (detector == null) {
                                        emptyList()
                                    } else if (bitmap.isRecycled) {
                                        sideStatus = "测速异常:bitmap"
                                        null
                                    } else {
                                        val boxes = detector.detect(bitmap)
                                        timings.putAll(detector.lastTimingsMs)
                                        val measured = SideVehicleGeometry.measurements(
                                            boxes, frame.width, frame.height, frame.roi, frame.ground_inverse)
                                        sideStatus = "运行中"
                                        timings["side_boxes"] = measured.size
                                        measured
                                    }
                                } catch (e: Exception) {
                                    if (e is CancellationException) throw e
                                    sideStatus = "测速异常:" + e.javaClass.simpleName
                                    android.util.Log.w("PhoneVisionSide", "side vehicle detector failed", e)
                                    null
                                }
                                timings["side_vehicle_ms"] = SystemClock.elapsedRealtime()-started
                            } else timings["side_detect"] = "skipped"
                            LaneLineState.publish(cpLane.lastLine, SystemClock.elapsedRealtime())
                            try {
                                val left = frame.roi["poly_left_norm"] ?: emptyList()
                                val right = frame.roi["poly_right_norm"] ?: emptyList()
                                if (left.size >= 3 || right.size >= 3) {
                                    val d = vasmDetector ?: VasmDetector(this@PhoneVisionService).also { vasmDetector = it }
                                    val l = if (left.size >= 3) d.confidence(bitmap, left) else -1f
                                    val r = if (right.size >= 3) d.confidence(bitmap, right) else -1f
                                    vasmStatus = "运行中"
                                    l to r
                                } else { vasmStatus = "缺少 ROI 多边形"; null }
                            } catch (e: Exception) {
                                if (e is CancellationException) throw e
                                vasmStatus = "盲区异常:" + (e.javaClass.simpleName) + ":" + (e.message ?: "").take(60)
                                android.util.Log.w("PhoneVisionVasm", "vasm failed", e)
                                null
                            }
                        } finally {
                            if (!bitmap.isRecycled) bitmap.recycle()
                        }
                        timings["detect_total_ms"] = SystemClock.elapsedRealtime()-beforeDetect
                        val elapsed = SystemClock.elapsedRealtime()-requestStarted
                        if (!PhoneVisionBudget.canSubmit(frame.capture_age_ms, elapsed, frame.bridge_wait_ms)) throw ExpiredVisionFrame()
                        if (packet.host != (PhoneVisionC3Address.navigationHost ?: host)) throw ExpiredVisionFrame()
                        val beforeTrack = SystemClock.elapsedRealtime()
                        val fresh = sideDetections?.let { tracker.update(it, frame.capture_mono_ns, frame.ego_speed_mps) }
                        val leftWire = publish("left", fresh, frame.capture_mono_ns)
                        val rightWire = publish("right", fresh, frame.capture_mono_ns)
                        val body = gson.toJson(mapOf("request_id" to frame.request_id, "frame_id" to frame.frame_id,
                            "left" to vasm?.first?.let { sidePayload(it, true, leftWire) },
                            "right" to vasm?.second?.let { sidePayload(it, false, rightWire) },
                            "lane_cp" to if (preferences.getBoolean("cp_lane_enabled", true)) laneCandidate else null,
                            "lane_line" to cpLane.lastLine?.let { mapOf("left" to it.leftType, "right" to it.rightType,
                                "left_conf" to it.leftConf, "right_conf" to it.rightConf) }))
                        timings["tracking_ms"] = SystemClock.elapsedRealtime()-beforeTrack
                        val post = Request.Builder().url("${packet.endpoint}/v1/observation").header("Authorization", "Bearer $token")
                            .post(body.toRequestBody("application/json".toMediaType())).build()
                        currentCoroutineContext().ensureActive()
                        val beforePost = SystemClock.elapsedRealtime()
                        client.newCall(post).execute().use { response ->
                            if (!response.isSuccessful) {
                                val rejection = response.body?.string()?.take(512).orEmpty()
                                if (PhoneVisionBudget.isExpiredRejection(response.code, rejection)) throw ExpiredVisionFrame()
                                error("结果被拒绝（${response.code}）")
                            }
                        }

                        timings["post_ms"] = SystemClock.elapsedRealtime()-beforePost
                        accepted++; timings["outcome"]="accepted"
                        fun line(wire: Map<String, Any>?): String {
                            if (wire == null) return "未确认车辆"
                            val distance = (wire["distance_m"] as? Double)?.let { "%.1f 米".format(it) } ?: "距离待标定"
                            val relative = (wire["relative_speed_mps"] as? Double)?.let { "相对速度 %+.1f km/h".format(it*3.6) } ?: "速度积累中"
                            val absolute = (wire["absolute_speed_mps"] as? Double)?.let { "；估计平均车速 %.1f km/h".format(it*3.6) } ?: ""
                            return "$distance；$relative$absolute"
                        }
                        val modelInfo=if (preferences.getBoolean("cp_lane_enabled",true)) cpLane.status else ""
                        availability.accepted(requestStarted, "手机运算 ${elapsed} ms\n左侧：${line(leftWire)}\n右侧：${line(rightWire)}\n车道模型：$modelInfo\n盲区模型：$vasmStatus\n测速模型：$sideStatus\n实验估算，限前方广角可见区域")
                    } catch (e: Exception) {
                        if (e is CancellationException) throw e
                        if (e is ExpiredVisionFrame) expired++
                        timings["outcome"] = if (e is ExpiredVisionFrame) "expired" else "error"
                        clearMotion()
                        availability.unavailable(e.message ?: "等待 C3 画面")
                        delay(if (e is ExpiredVisionFrame) 80 else 1000)
                    } finally {
                                                timings["total_ms"] = SystemClock.elapsedRealtime()-requestStarted
                        timings["report_elapsed_ms"] = SystemClock.elapsedRealtime()
                        timings["fetch_attempts"] = fetchAttempts.get()
                        timings["prefetched_total"] = prefetched?.completedFetches?.get() ?: 0L
                        timings["accepted_total"] = accepted; timings["expired_total"] = expired; timings["duplicates_total"] = duplicates
                        lastTimingReport = timings.toMap()
                    }
                    if (prefetchEnabled) delay(minimumIdleMs)
                    else delay(maxOf(minimumIdleMs, 1000L/targetFps-(SystemClock.elapsedRealtime()-start)))
                }
            }
        } finally {
            cpLane.close(); prefetched?.close()
            sideDetector?.close(); sideDetector = null
        }
    }

    private var leftHits = 0
    private var rightHits = 0

    /** Consecutive occupied frames, so the device's hits>=3 gate means "stable detection". */
    private fun sidePayload(occupied: Float, left: Boolean, speed: Map<String, Any>? = null): Map<String, Any> {
        // The device store requires hits >= 1, so an idle side keeps the minimum count.
        // hits / confidence / occupied stay the blind-spot contract. Speed is optional beside them.
        val hits = if (occupied >= OCCUPIED_THRESHOLD) {
            (if (left) leftHits else rightHits).also { if (left) leftHits++ else rightHits++ }
        } else {
            if (left) leftHits = 0 else rightHits = 0
            1
        }
        val blind = mapOf<String, Any>("hits" to hits, "confidence" to occupied.coerceIn(0f, 1f), "occupied" to occupied.coerceIn(0f, 1f))
        return mergeSidePayload(blind, speed)
    }

    override fun onDestroy() {
        availability.stopped()
        scope.cancel()
        wakeLock?.let { if (it.isHeld) it.release() }
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}
