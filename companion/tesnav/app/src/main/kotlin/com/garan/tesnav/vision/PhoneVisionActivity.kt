package com.garan.tesnav.vision

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.*
import kotlinx.coroutines.*

class PhoneVisionActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val preferences = getSharedPreferences("phone_vision", MODE_PRIVATE)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32, 40, 32, 24) }
        val title = TextView(this).apply { text = "手机侧方车辆识别"; textSize = 24f }
        val description = TextView(this).apply { text = "单路广角画面由 C3 提供，车辆识别在手机上运算。原车盲区保护独立保留。" }
        val host = EditText(this).apply { hint = "C3 地址"; setSingleLine(true)
            setText(preferences.getString("host", intent.getStringExtra("c3_host") ?: "comma-904f361e.local")) }
        val token = EditText(this).apply { hint = "设备连接码"; setSingleLine(true)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setText(preferences.getString("token", "")) }
        val lane = Switch(this).apply { text = "实验：本车车道模型估计"; isChecked = preferences.getBoolean("cp_lane_enabled", false)
            setOnCheckedChangeListener { _, checked -> preferences.edit().putBoolean("cp_lane_enabled", checked).apply() } }
        val night = Switch(this).apply { text = "使用夜间车道模型"; isChecked = preferences.getBoolean("cp_lane_night", false)
            setOnCheckedChangeListener { _, checked -> preferences.edit().putBoolean("cp_lane_night", checked).apply() } }
        val laneNotice = TextView(this).apply { text = "默认关闭。模型只提供可见车道估计，缺模型或结果不可靠时显示未知；不会开启 C3 导航或授权变道。" }
        val status = TextView(this).apply { textSize = 18f; setPadding(0, 24, 0, 24) }
        val start = Button(this).apply { text = "开始手机运算"; setOnClickListener {
            if (host.text.isBlank() || token.text.length < 32) { Toast.makeText(this@PhoneVisionActivity, "请填写 C3 地址与连接码", Toast.LENGTH_SHORT).show(); return@setOnClickListener }
            preferences.edit().putString("host", host.text.toString().trim()).putString("token", token.text.toString().trim())
                .apply()
            startForegroundService(Intent(this@PhoneVisionActivity, PhoneVisionService::class.java))
        } }
        val stop = Button(this).apply { text = "停止"; setOnClickListener { stopService(Intent(this@PhoneVisionActivity, PhoneVisionService::class.java)); PhoneVisionService.status.value = "已停止" } }
        val back = Button(this).apply { text = "返回导航，保持运算"; setOnClickListener { finish() } }
        listOf(title, description, host, token, lane, night, laneNotice, start, stop, back, status).forEach { layout.addView(it) }
        setContentView(ScrollView(this).apply { addView(layout) })
        scope.launch { PhoneVisionService.status.collect { status.text = it } }
    }
    override fun onDestroy() { scope.cancel(); super.onDestroy() }
}
