package com.garan.tesnav.vision

import android.app.Service
import android.content.Intent
import android.os.*

/** Non-exported, separate process: a JNI crash cannot terminate navigation. */
class CpLaneNativeService : Service() {
    private lateinit var engine: CpLaneNativeEngine
    private lateinit var messenger: Messenger
    override fun onCreate() {
        super.onCreate()
        engine = CpLaneNativeEngine(this)
        messenger = Messenger(Handler(Looper.getMainLooper()) { request ->
            if (request.what != 1) return@Handler false
            val d = request.data
            val width = d.getInt("width"); val height = d.getInt("height")
            val y = d.getByteArray("y")
            val model = d.getString("model") ?: ""
            val accepted = width in 320..640 && height in 200..480 && y != null && y.size == width * height
                && model in setOf("vlaneDay.mnn", "vlaneNight.mnn")
            val result = if (accepted) engine.detect(y!!, width, height, model, d.getBoolean("road")) else null
            val reply = Message.obtain(null, 1).apply {
                arg1 = request.arg1
                data = Bundle().apply {
                    putBoolean("valid", result != null)
                    putString("status", engine.status)
                    result?.let { putInt("left", it.leftClass); putInt("right", it.rightClass); putString("model", it.model) }
                    if (accepted && d.getBoolean("road")) engine.road?.let {
                        putInt("roadH",it.height); putInt("roadW",it.width)
                        putByteArray("roadIds",it.ids); putByteArray("roadConfidence",it.confidence)
                    }
                }
            }
            try { request.replyTo?.send(reply) } catch (_: RemoteException) { }
            true
        })
    }
    override fun onBind(intent: Intent): IBinder = messenger.binder
    override fun onDestroy() { engine.close(); super.onDestroy() }
}
