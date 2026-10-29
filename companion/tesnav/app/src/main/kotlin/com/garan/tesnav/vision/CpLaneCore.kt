package com.garan.tesnav.vision

internal data class CpLaneResult(
    val version: Int = 1, val model: String, val leftClass: Int, val rightClass: Int,
    val laneNumber: Int, val laneCount: Int, val scope: String = "visibleCorridor",
    val control_eligible: Boolean = false,
)

/** Two four-class heads, as exposed by CP's compact lane JNI ABI.
 * Class 0 is unavailable; 1..3 are candidate left/right lane positions.
 * These classes do not prove that every lane or the carriageway edge is visible. */
internal object CpLaneCore {
    fun decode(scores: FloatArray, model: String): CpLaneResult? {
        if (model !in setOf("vlaneDay.mnn", "vlaneNight.mnn") || scores.size != 8 || scores.any { !it.isFinite() }) return null
        fun pick(start: Int): Int? {
            val ranked = (0..3).sortedByDescending { scores[start + it] }
            val best = ranked[0]
            if (best == 0 || scores[start + best] - scores[start + ranked[1]] <= 0.1f) return null
            return best
        }
        val left = pick(0) ?: return null
        val right = pick(4) ?: return null
        return CpLaneResult(model = model, leftClass = left, rightClass = right,
            laneNumber = left, laneCount = left + right - 1)
    }

    fun luma(pixels: IntArray): ByteArray = ByteArray(pixels.size) { i ->
        val p = pixels[i]
        val red = (p ushr 16) and 255; val green = (p ushr 8) and 255; val blue = p and 255
        (16 + ((66 * red + 129 * green + 25 * blue + 128) shr 8)).coerceIn(16, 235).toByte()
    }
}
