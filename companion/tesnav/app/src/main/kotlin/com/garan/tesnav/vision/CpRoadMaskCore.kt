package com.garan.tesnav.vision

/** Channel IDs have deliberately unassigned semantics until labelled replay validation. */
internal data class CpRoadMask(val height: Int, val width: Int, val ids: ByteArray,
    val confidence: ByteArray, val semantics: String = "unmapped", val controlEligible: Boolean = false)

internal data class CpLaneInference(val lane: CpLaneResult?, val road: CpRoadMask?)

internal object CpRoadMaskCore {
    private fun pixels(height: Int, width: Int): Int? =
        if (height in 1..192 && width in 1..512) height*width else null

    fun size(shape: IntArray): Int? {
        if (shape.size != 4 || shape[2] != 4 || shape[3] !in 0..1) return null
        return pixels(shape[0],shape[1])?.times(4)
    }

    fun fromPacket(height: Int, width: Int, ids: ByteArray?, confidence: ByteArray?): CpRoadMask? {
        val n=pixels(height,width) ?: return null
        if (ids==null || confidence==null || ids.size!=n || confidence.size!=n ||
            ids.any { it.toInt() !in 0..3 }) return null
        return CpRoadMask(height,width,ids,confidence)
    }

    fun fromScores(shape: IntArray, scores: FloatArray): CpRoadMask? {
        val total=size(shape) ?: return null
        if (scores.size!=total) return null
        val n=total/4; val ids=ByteArray(n); val confidence=ByteArray(n)
        for (i in 0 until n) {
            var best=0; var high=-1f; var sum=0f
            for (c in 0..3) {
                val v=scores[if(shape[3]==1) i*4+c else c*n+i]
                if (!v.isFinite() || v < -.001f || v > 1.001f) return null
                sum+=v
                if (v>high) { high=v; best=c }
            }
            if (sum !in .98f..1.02f) return null
            ids[i]=best.toByte(); confidence[i]=(high*255).toInt().coerceIn(0,255).toByte()
        }
        return CpRoadMask(shape[0],shape[1],ids,confidence)
    }
}
