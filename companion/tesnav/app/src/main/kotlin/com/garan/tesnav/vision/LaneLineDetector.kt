package com.garan.tesnav.vision

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import java.io.Closeable
import java.nio.FloatBuffer
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

internal data class LaneLineResult(
    val leftType: Int, val rightType: Int, val leftConf: Float, val rightConf: Float, val candidates: Int,
)

private class LaneBox(
    val cx: Float, val cy: Float, val w: Float, val h: Float,
    val score: Float, val cls: Int, val coeff: FloatArray,
) {
    fun iou(other: LaneBox): Float {
        val ax1 = cx - w / 2; val ay1 = cy - h / 2; val ax2 = cx + w / 2; val ay2 = cy + h / 2
        val bx1 = other.cx - other.w / 2; val by1 = other.cy - other.h / 2
        val bx2 = other.cx + other.w / 2; val by2 = other.cy + other.h / 2
        val iw = max(0f, min(ax2, bx2) - max(ax1, bx1))
        val ih = max(0f, min(ay2, by2) - max(ay1, by1))
        val inter = iw * ih
        val union = w * h + other.w * other.h - inter
        return if (union > 0f) inter / union else 0f
    }
}

/** YOLOv8-seg lane-boundary classifier (lane.onnx), ported from carrot/xiaoge lane_inference.py. */
internal class LaneLineDetector(context: Context, cpuThreads: Int = 2) : Closeable {
    private val environment = OrtEnvironment.getEnvironment()
    private val session: OrtSession

    init {
        val model = context.assets.open("lane.onnx").use { it.readBytes() }
        OrtSession.SessionOptions().use { options ->
            options.setIntraOpNumThreads(cpuThreads.coerceIn(1, 4))
            options.setInterOpNumThreads(1)
            session = environment.createSession(model, options)
        }
    }

    fun detect(y: ByteArray, width: Int, height: Int): LaneLineResult? {
        require(y.size >= width * height) { "short Y plane" }
        val input = FloatArray(3 * INPUT * INPUT)
        val crop = min(width, height)
        val x0 = (width - crop) / 2
        val y0 = (height - crop) / 2
        for (row in 0 until INPUT) {
            val sy = y0 + row * crop / INPUT
            for (col in 0 until INPUT) {
                val sx = x0 + col * crop / INPUT
                val v = (y[sy * width + sx].toInt() and 255) / 255f
                val base = row * INPUT + col
                input[base] = v
                input[INPUT * INPUT + base] = v
                input[2 * INPUT * INPUT + base] = v
            }
        }
        val shape = longArrayOf(1, 3, INPUT.toLong(), INPUT.toLong())
        OnnxTensor.createTensor(environment, FloatBuffer.wrap(input), shape).use { tensor ->
            session.run(mapOf("images" to tensor)).use { outputs ->
                val pred = ((outputs.get("output0").orElseThrow().value) as Array<Array<FloatArray>>)[0]
                val proto = ((outputs.get("output1").orElseThrow().value) as Array<Array<Array<FloatArray>>>)[0]
                return decode(pred, proto)
            }
        }
    }

    private fun decode(pred: Array<FloatArray>, proto: Array<Array<FloatArray>>): LaneLineResult {
        val anchors = pred[0].size
        val boxes = ArrayList<LaneBox>()
        for (a in 0 until anchors) {
            var best = -Float.MAX_VALUE
            var bestClass = 0
            for (c in 0 until 6) {
                val s = pred[4 + c][a]
                if (s > best) { best = s; bestClass = c }
            }
            if (best < CONF) continue
            boxes += LaneBox(pred[0][a], pred[1][a], pred[2][a], pred[3][a], best, bestClass,
                FloatArray(32) { pred[10 + it][a] })
        }

        val keep = ArrayList<LaneBox>()
        val suppressed = BooleanArray(boxes.size)
        for (i in boxes.indices.sortedByDescending { boxes[it].score }) {
            if (suppressed[i]) continue
            keep += boxes[i]
            for (j in boxes.indices) {
                if (j == i || suppressed[j] || boxes[j].cls != boxes[i].cls) continue
                if (boxes[i].iou(boxes[j]) > IOU) suppressed[j] = true
            }
        }

        data class Candidate(val type: Int, val score: Float, val bottom: Int, val center: Float)
        val candidates = ArrayList<Candidate>()
        for (box in keep) {
            if (box.cls in IGNORED) continue
            fun clampProto(v: Float) = v.coerceIn(0f, (PROTO - 1).toFloat()).toInt()
            val leftP = clampProto((box.cx - box.w / 2) / INPUT * PROTO)
            val topP = clampProto((box.cy - box.h / 2) / INPUT * PROTO)
            val rightP = clampProto((box.cx + box.w / 2) / INPUT * PROTO)
            val bottomP = clampProto((box.cy + box.h / 2) / INPUT * PROTO)
            if (rightP <= leftP || bottomP <= topP) continue
            val w = rightP - leftP + 1
            val h = bottomP - topP + 1
            val mask = BooleanArray(w * h)
            var any = false
            for (yy in 0 until h) for (xx in 0 until w) {
                var acc = 0f
                for (k in 0 until 32) acc += box.coeff[k] * proto[k][topP + yy][leftP + xx]
                if (acc > 0f) { mask[yy * w + xx] = true; any = true }
            }
            if (!any) continue
            var lowest = -1
            for (yy in h - 1 downTo 0) {
                var hit = false
                for (xx in 0 until w) if (mask[yy * w + xx]) { hit = true; break }
                if (hit) { lowest = yy; break }
            }
            if (lowest < 0) continue
            val bottomY = topP + lowest
            if (bottomY < PROTO / 2) continue
            var sum = 0
            var count = 0
            for (xx in 0 until w) if (mask[lowest * w + xx]) { sum += xx; count++ }
            if (count == 0) continue
            candidates += Candidate(typeOf(box.cls), box.score, bottomY, leftP + sum.toFloat() / count)
        }

        fun nearest(left: Boolean): Pair<Int, Float> {
            val pool = candidates.filter { if (left) it.center < CENTER else it.center >= CENTER }
            val best = pool.minByOrNull { (it.center - CENTER).pow(2) + 2f * (it.bottom - (PROTO - 1)).toFloat().pow(2) }
            return (best?.type ?: -1) to (best?.score ?: 0f)
        }
        val l = nearest(true)
        val r = nearest(false)
        return LaneLineResult(l.first, r.first, l.second, r.second, candidates.size)
    }

    private fun typeOf(cls: Int) = when (cls) {
        in SOLID -> 1
        in DASHED -> 0
        else -> -1
    }

    override fun close() { session.close() }

    private companion object {
        const val INPUT = 416
        const val PROTO = 104
        const val CONF = 0.25f
        const val IOU = 0.5f
        const val CENTER = PROTO / 2f
        val SOLID = setOf(0, 2, 5)
        val DASHED = setOf(1)
        val IGNORED = setOf(3, 4)
    }
}
