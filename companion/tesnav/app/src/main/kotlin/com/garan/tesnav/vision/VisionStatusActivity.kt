package com.garan.tesnav.vision

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** 只读状态页：手机侧视觉/车道/盲区的实时结果，方便路测对账。 */
class VisionStatusActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var service: TextView
    private lateinit var lane: TextView
    private lateinit var paint: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 40, 32, 24)
        }
        val title = TextView(this).apply { text = "视觉与车道状态（只读）"; textSize = 22f }
        service = TextView(this).apply { textSize = 16f; setPadding(0, 16, 0, 12) }
        lane = TextView(this).apply { textSize = 16f; setPadding(0, 8, 0, 12) }
        paint = TextView(this).apply { textSize = 16f; setPadding(0, 8, 0, 12) }
        val note = TextView(this).apply {
            text = "数据来自手机本地：车道模型(MNN)、标线类型(ONNX)、盲区(VASM)。\nC3 侧超车状态需要协议扩展，暂未显示。"
            textSize = 13f
        }
        val back = Button(this).apply {
            text = "返回"
            setOnClickListener { finish() }
        }
        val views: List<View> = listOf(title, service, lane, paint, note, back)
        views.forEach { layout.addView(it) }
        setContentView(ScrollView(this).apply { addView(layout) })
    }

    override fun onResume() {
        super.onResume()
        handler.post(tick)
    }

    override fun onPause() {
        handler.removeCallbacks(tick)
        super.onPause()
    }

    private val tick = object : Runnable {
        override fun run() {
            service.text = "视觉服务：" + PhoneVisionService.status.value
            val now = SystemClock.elapsedRealtime()
            val frame = LaneLineState.fresh(LaneLineState.state.value, now)
            paint.text = frame?.let { LaneLineState.text(it.result) } ?: "车道线类型：暂无数据"
            lane.text = "车道位置：由手机模型估算并上报 C3（页面暂不展示）"
            handler.postDelayed(this, 500)
        }
    }
}
