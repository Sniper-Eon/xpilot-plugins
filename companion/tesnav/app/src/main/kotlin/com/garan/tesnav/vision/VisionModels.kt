package com.garan.tesnav.vision

import android.content.SharedPreferences
import android.graphics.Bitmap

/**
 * 白天/夜间车道模型选择。
 * 默认自动：按当前帧平均亮度迟滞切换（亮 > 95 白天，暗 < 75 夜间），中间保持上一次；
 * 关闭自动后沿用「夜间模型」开关强制选择。
 */
internal object VisionModels {
    const val DAY = "vlaneDay.mnn"
    const val NIGHT = "vlaneNight.mnn"
    private const val KEY_STATE = "cp_lane_night_auto_state"
    private const val DAY_LUMA = 95f
    private const val NIGHT_LUMA = 75f

    fun meanLuma(bitmap: Bitmap): Int {
        val step = maxOf(1, minOf(bitmap.width, bitmap.height) / 32)
        var total = 0L
        var count = 0
        var y = 0
        while (y < bitmap.height) {
            var x = 0
            while (x < bitmap.width) {
                val p = bitmap.getPixel(x, y)
                val r = (p shr 16) and 0xFF
                val g = (p shr 8) and 0xFF
                val b = p and 0xFF
                total += (r * 66 + g * 129 + b * 25 + 128) shr 8
                count++
                x += step
            }
            y += step
        }
        return if (count == 0) 128 else (total / count).toInt()
    }

    fun select(preferences: SharedPreferences, meanLuma: Int): String {
        if (!preferences.getBoolean("cp_lane_auto", true)) {
            return if (preferences.getBoolean("cp_lane_night", false)) NIGHT else DAY
        }
        val previousNight = preferences.getBoolean(KEY_STATE, false)
        val night = when {
            meanLuma >= DAY_LUMA -> false
            meanLuma <= NIGHT_LUMA -> true
            else -> previousNight
        }
        if (night != previousNight) preferences.edit().putBoolean(KEY_STATE, night).apply()
        return if (night) NIGHT else DAY
    }
}
