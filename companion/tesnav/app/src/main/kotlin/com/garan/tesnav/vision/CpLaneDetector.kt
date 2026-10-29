package com.garan.tesnav.vision

import android.content.*
import android.graphics.Bitmap
import android.os.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull

/** Bounded one-frame IPC. No queue, reused result, direct JNI or control output. */
internal class CpLaneDetector(private val context: Context) : AutoCloseable {
    @Volatile private var binding = false
    @Volatile private var connected = CompletableDeferred<Messenger?>()
    @Volatile private var pending: CompletableDeferred<CpLaneResult?>? = null
    @Volatile private var serial = 0
    @Volatile private var busy = 0
    @Volatile var status = "未启用车道模型"
        private set
    private val replies = Messenger(Handler(Looper.getMainLooper()) { reply ->
        if (reply.arg1 == busy && busy != 0) {
            val waiting = pending
            val d = reply.data
            status = d.getString("status") ?: "车道模型未知"
            val left = d.getInt("left"); val right = d.getInt("right")
            val model = d.getString("model") ?: ""
            val result = if (d.getBoolean("valid") && left in 1..3 && right in 1..3
                && model in setOf("vlaneDay.mnn", "vlaneNight.mnn"))
                CpLaneResult(model = model, leftClass = left, rightClass = right, laneNumber = left, laneCount = left + right - 1) else null
            pending = null
            waiting?.complete(result)
            busy = 0
        }
        true
    })
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, service: IBinder) { connected.complete(Messenger(service)) }
        override fun onServiceDisconnected(name: ComponentName) {
            pending?.complete(null); busy = 0
            connected = CompletableDeferred()
            status = "车道模型进程已断开"
        }
        override fun onBindingDied(name: ComponentName) { close(); status = "车道模型进程已退出" }
        override fun onNullBinding(name: ComponentName) { connected.complete(null) }
    }

    suspend fun detect(bitmap: Bitmap, model: String): CpLaneResult? {
        if (busy != 0) { status = "车道模型仍在处理，当前帧跳过"; return null }
        if (bitmap.width !in 320..640 || bitmap.height !in 200..480) { status = "车道模型图像尺寸不支持"; return null }
        return try {
            if (!binding) {
                binding = context.bindService(Intent(context, CpLaneNativeService::class.java), connection, Context.BIND_AUTO_CREATE)
                if (!binding) { status = "车道模型进程无法启动"; return null }
            }
            val worker = withTimeoutOrNull(500) { connected.await() } ?: run { status = "等待车道模型进程"; return null }
            val pixels = IntArray(bitmap.width * bitmap.height)
            bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
            val result = CompletableDeferred<CpLaneResult?>()
            pending = result; serial++; busy = serial
            worker.send(Message.obtain(null, 1).apply {
                arg1 = serial; replyTo = replies
                data = Bundle().apply { putByteArray("y", CpLaneCore.luma(pixels)); putInt("width", bitmap.width)
                    putInt("height", bitmap.height); putString("model", model) }
            })
            val observation = withTimeoutOrNull(500) { result.await() }
            if (!result.isCompleted) status = "车道模型超时，本帧未知"
            observation
        } catch (_: RemoteException) { close(); status = "车道模型进程不可用"; null }
          catch (_: SecurityException) { close(); status = "车道模型连接被拒绝"; null }
    }
    override fun close() {
        pending?.complete(null); pending = null; busy = 0
        if (binding) try { context.unbindService(connection) } catch (_: IllegalArgumentException) { }
        binding = false; connected = CompletableDeferred()
    }
}
