package com.garan.tesnav.vision

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Path
import java.io.Closeable
import java.nio.FloatBuffer
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Blind-spot occupancy classifier (v_asm_model.onnx), ported from carrot/xiaoge v_asm_inference.py. */
internal class VasmDetector(context: Context, cpuThreads: Int = 2) : Closeable {
    private val environment = OrtEnvironment.getEnvironment()
    private val session: OrtSession

    init {
        val model = context.assets.open("v_asm_model.onnx").use { it.readBytes() }
        OrtSession.SessionOptions().use { options ->
            options.setIntraOpNumThreads(cpuThreads.coerceIn(1, 4))
            options.setInterOpNumThreads(1)
            session = environment.createSession(model, options)
        }
    }

    /** Fraction of the ROI polygon occupied by a near vehicle; second output head, as in the reference. */
    fun confidence(bitmap: Bitmap, polygonNorm: List<List<Double>>): Float {
        if (polygonNorm.size < 3) return 0f
        val points = polygonNorm.map { (it[0] * bitmap.width).toFloat() to (it[1] * bitmap.height).toFloat() }
        val minX = points.minOf { it.first }.toInt().coerceIn(0, bitmap.width - 2)
        val minY = points.minOf { it.second }.toInt().coerceIn(0, bitmap.height - 2)
        val maxX = points.maxOf { it.first }.toInt().coerceIn(minX + 2, bitmap.width)
        val maxY = points.maxOf { it.second }.toInt().coerceIn(minY + 2, bitmap.height)
        val cropW = (maxX - minX) / 2 * 2
        val cropH = (maxY - minY) / 2 * 2
        if (cropW < 2 || cropH < 2) return 0f

        val crop = Bitmap.createBitmap(cropW, cropH, Bitmap.Config.ARGB_8888)
        try {
            val canvas = Canvas(crop)
            canvas.drawColor(Color.BLACK)
            // Keep only the ROI polygon, everything else stays black.
            val path = Path().apply {
                points.forEachIndexed { i, (x, y) ->
                    val px = x - minX; val py = y - minY
                    if (i == 0) moveTo(px, py) else lineTo(px, py)
                }
                close()
            }
            canvas.save()
            canvas.clipPath(path)
            canvas.drawBitmap(bitmap, -minX.toFloat(), -minY.toFloat(), null)
            canvas.restore()

            val scale = INPUT / max(cropW, cropH).toFloat()
            val resizedW = max(1, (cropW * scale).roundToInt())
            val resizedH = max(1, (cropH * scale).roundToInt())
            val resized = Bitmap.createScaledBitmap(crop, resizedW, resizedH, true)
            try {
                val square = Bitmap.createBitmap(INPUT, INPUT, Bitmap.Config.ARGB_8888)
                Canvas(square).apply {
                    drawColor(Color.BLACK)
                    drawBitmap(resized, ((INPUT - resizedW) / 2).toFloat(), ((INPUT - resizedH) / 2).toFloat(), null)
                }
                val input = FloatArray(3 * INPUT * INPUT)
                val pixels = IntArray(INPUT * INPUT)
                square.getPixels(pixels, 0, INPUT, 0, 0, INPUT, INPUT)
                for (i in pixels.indices) {
                    val p = pixels[i]
                    input[i] = ((p shr 16) and 255) / 255f
                    input[INPUT * INPUT + i] = ((p shr 8) and 255) / 255f
                    input[2 * INPUT * INPUT + i] = (p and 255) / 255f
                }
                val shape = longArrayOf(1, 3, INPUT.toLong(), INPUT.toLong())
                OnnxTensor.createTensor(environment, FloatBuffer.wrap(input), shape).use { tensor ->
                    session.run(mapOf("images" to tensor)).use { outputs ->
                        val value = outputs.get(0).value
                        val flat = flatten(value)
                        return if (flat.size >= 2) flat[1] else 0f
                    }
                }
            } finally {
                resized.recycle()
            }
        } finally {
            crop.recycle()
        }
    }

    private fun flatten(value: Any?): FloatArray = when (value) {
        is Array<*> -> value.flatMap { flatten(it).toList() }.toFloatArray()
        is FloatArray -> value
        is Float -> floatArrayOf(value)
        else -> FloatArray(0)
    }

    override fun close() { session.close() }

    private companion object { const val INPUT = 352 }
}
