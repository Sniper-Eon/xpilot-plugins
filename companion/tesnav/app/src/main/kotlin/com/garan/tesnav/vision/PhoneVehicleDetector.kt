package com.garan.tesnav.vision

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import java.io.Closeable
import java.nio.FloatBuffer

/**
 * side_vehicle320.onnx, used only for side-lane distance and speed.
 * Blind-spot occupancy stays on [VasmDetector].
 *
 * The shared camera bitmap is never recycled here. Callers must keep it alive
 * until blind-spot scoring has also finished; recycling it first is what made
 * the later model return no score.
 */
internal class PhoneVehicleDetector(context: Context, cpuThreads: Int = 2, modelAsset: String = "side_vehicle320.onnx") : Closeable {
    var lastTimingsMs: Map<String, Long> = emptyMap()
        private set
    private val environment = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val inputSize: Int

    init {
        require(modelAsset == "side_vehicle320.onnx")
        val model = context.assets.open(modelAsset).use { it.readBytes() }
        OrtSession.SessionOptions().use { options ->
            options.setIntraOpNumThreads(cpuThreads.coerceIn(1, 4))
            options.setInterOpNumThreads(1)
            val loaded = environment.createSession(model, options)
            try {
                val shape = (loaded.inputInfo["images"]?.info as? TensorInfo)?.shape
                    ?: error("模型缺少图像输入")
                require(shape.size == 4 && shape[0] == 1L && shape[1] == 3L && shape[2] == shape[3] &&
                    shape[2] == 320L) { "模型输入尺寸不支持" }
                inputSize = shape[2].toInt()
                session = loaded
            } catch (e: Exception) {
                loaded.close()
                throw e
            }
        }
    }

    fun detect(bitmap: Bitmap): List<VehicleBox> {
        val clockStart = android.os.SystemClock.elapsedRealtimeNanos()
        if (bitmap.isRecycled || bitmap.width <= 1 || bitmap.height <= 1) {
            lastTimingsMs = mapOf("preprocess_ms" to 0L, "inference_ms" to 0L, "output_ms" to 0L)
            return emptyList()
        }
        val size = inputSize
        val placed = SideVehicleGeometry.letterbox(bitmap.width, bitmap.height, size)
        // Private software canvas. Drawing the source copies pixels even when the
        // decoded frame is hardware-backed or not ARGB_8888, and only this copy is recycled.
        val square = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        try {
            val canvas = Canvas(square)
            canvas.drawColor(Color.rgb(114, 114, 114))
            canvas.drawBitmap(
                bitmap,
                null,
                Rect(placed.dx, placed.dy, placed.dx + placed.contentWidth, placed.dy + placed.contentHeight),
                Paint(Paint.FILTER_BITMAP_FLAG),
            )
            val pixels = IntArray(size * size)
            square.getPixels(pixels, 0, size, 0, 0, size, size)
            val input = planarRgb(pixels)
            OnnxTensor.createTensor(environment, FloatBuffer.wrap(input), longArrayOf(1, 3, size.toLong(), size.toLong())).use { tensor ->
                val beforeRun = android.os.SystemClock.elapsedRealtimeNanos()
                session.run(mapOf("images" to tensor)).use { result ->
                    val afterRun = android.os.SystemClock.elapsedRealtimeNanos()
                    val rows = detectionRows(result[0].value)
                    val boxes = if (rows == null) emptyList() else SideVehicleGeometry.decode(rows, bitmap.width, bitmap.height, size)
                    val afterDecode = android.os.SystemClock.elapsedRealtimeNanos()
                    lastTimingsMs = mapOf(
                        "preprocess_ms" to (beforeRun - clockStart) / 1_000_000,
                        "inference_ms" to (afterRun - beforeRun) / 1_000_000,
                        "output_ms" to (afterDecode - afterRun) / 1_000_000,
                    )
                    return boxes
                }
            }
        } finally {
            if (!square.isRecycled) square.recycle()
        }
    }

    /** Model output is [1, 5, N] (cx, cy, w, h, confidence). A transposed batch is accepted too. */
    private fun detectionRows(value: Any?): Array<FloatArray>? {
        val batch = value as? Array<*> ?: return null
        val first = batch.firstOrNull() ?: return null
        if (first is Array<*>) {
            val matrix = first.filterIsInstance<FloatArray>()
            if (matrix.size == 5 && matrix.all { it.size == matrix[0].size }) return matrix.toTypedArray()
            if (matrix.isNotEmpty() && matrix.all { it.size == 5 }) {
                val count = matrix.size
                return Array(5) { row -> FloatArray(count) { col -> matrix[col][row] } }
            }
        }
        return null
    }

    override fun close() {
        session.close()
    }
}
