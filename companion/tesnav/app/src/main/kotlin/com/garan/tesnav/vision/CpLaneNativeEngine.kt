package com.garan.tesnav.vision

import android.content.Context
import com.google.gson.Gson
import com.jixiexiaoge.drivingassist.vision.LaneNative
import java.io.File
import java.security.MessageDigest

/** Optional private-reference runtime. Missing assets/native errors remain unavailable;
 * no model download, feature auto-enable, navigation or control command. */
internal class CpLaneNativeEngine(private val context: Context) : AutoCloseable {
    private var native: LaneNative? = null
    private var handle = 0L
    private var selected = ""
    private var failedModel = ""
    private var roadScores = FloatArray(0)
    var road: CpRoadMask? = null
        private set
    var status = "未启用车道模型"
        private set

    private fun digest(file: File): String = file.inputStream().use { input ->
        val hash = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(65536)
        while (true) { val n = input.read(buffer); if (n < 0) break; hash.update(buffer, 0, n) }
        hash.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
    }

    private fun prepare(model: String): Boolean {
        if (model == failedModel) return false
        if (handle != 0L && selected == model) return true
        close()
        return try {
            val meta = context.assets.open("cp-lane-assets.json").bufferedReader().use { it.readText() }
            val manifest = Gson().fromJson(meta, com.google.gson.JsonObject::class.java)
            val expected = manifest.getAsJsonObject("sha256").get("assets/models/$model").asString
            require(expected.matches(Regex("[0-9a-f]{64}")))
            val target = File(context.filesDir, "cp-lane/$model")
            target.parentFile!!.mkdirs()
            if (!target.isFile || digest(target) != expected) {
                val temporary = File(target.parentFile, "$model.tmp")
                context.assets.open("models/$model").use { source -> temporary.outputStream().use { source.copyTo(it) } }
                check(digest(temporary) == expected) { "车道模型校验失败" }
                check(temporary.renameTo(target))
            }
            LaneNative.load()
            val runtime = LaneNative()
            check(runtime.nativeLoadStatus() == "ok") { "车道模型运行库不可用" }
            native = runtime
            handle = runtime.nativeInit(target.absolutePath)
            check(handle != 0L) { "车道模型加载失败" }
            runtime.nativeSetRoi(0f, 0f)
            selected = model
            status = "车道模型已加载，等待有效画面"
            true
        } catch (e: Exception) {
            close(); failedModel = model; status = "车道模型不可用：${e.javaClass.simpleName}"; false
        } catch (e: LinkageError) {
            close(); failedModel = model; status = "车道模型运行库不可用"; false
        }
    }

    fun detect(y: ByteArray, width: Int, height: Int, model: String, roadEnabled: Boolean = false): CpLaneResult? {
        road = null
        if (!prepare(model)) return null
        return try {
            val shape = if (roadEnabled) try { native!!.nativeRoadShape(handle) }
                catch (_: LinkageError) { IntArray(0) } else IntArray(0)
            val roadSize = CpRoadMaskCore.size(shape) ?: 0
            if (roadScores.size != roadSize) roadScores = FloatArray(roadSize)
            roadScores.fill(Float.NaN) // An incomplete JNI copy must not reuse the previous frame.
            val scores = FloatArray(8) { Float.NaN }
            val rc = native!!.nativeInferCompact(handle, y, width, height,
                width, roadScores, scores)
            if (rc == 0 && roadSize > 0) road = CpRoadMaskCore.fromScores(shape,roadScores)
            val result = if (rc == 0) CpLaneCore.decode(scores, model) else null
            status = if (rc != 0) "车道模型推理返回错误 $rc" else result?.let { "视觉估计：第 ${it.laneNumber}/${it.laneCount} 可见车道（估计）" }
                ?: "车道模型本帧未确认"
            result
        } catch (e: Exception) { status = "车道模型本帧失败"; null }
          catch (e: LinkageError) { status = "车道模型运行库失败"; null }
    }

    override fun close() {
        road = null; roadScores = FloatArray(0)
        val current = handle; handle = 0L; selected = ""
        if (current != 0L) try { native?.nativeRelease(current) } catch (_: Exception) { } catch (_: LinkageError) { }
        native = null
    }
}
