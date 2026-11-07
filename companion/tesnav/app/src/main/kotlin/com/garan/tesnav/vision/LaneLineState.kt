package com.garan.tesnav.vision

import kotlinx.coroutines.flow.MutableStateFlow

/** Last lane-boundary classification produced by the phone vision service, for the navigation overlay. */
internal object LaneLineState {
    data class Frame(val result: LaneLineResult, val issuedMs: Long)

    val state = MutableStateFlow<Frame?>(null)

    /** The result is a live observation: anything older than this is treated as unknown. */
    const val maxAgeMs = 2_000L

    fun publish(result: LaneLineResult?, elapsedMs: Long) {
        state.value = result?.let { Frame(it, elapsedMs) }
    }

    fun fresh(frame: Frame?, elapsedMs: Long): Frame? =
        frame?.takeIf { elapsedMs - it.issuedMs in 0..maxAgeMs }

    fun text(result: LaneLineResult): String {
        fun name(type: Int) = when (type) {
            1 -> "实线"
            0 -> "虚线"
            else -> "未知"
        }
        return "车道线：左${name(result.leftType)} · 右${name(result.rightType)}"
    }
}
