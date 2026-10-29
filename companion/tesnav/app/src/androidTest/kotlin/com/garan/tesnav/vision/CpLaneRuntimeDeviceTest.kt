package com.garan.tesnav.vision

import android.graphics.Bitmap
import android.os.Bundle
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic image native-runtime smoke only. No C3 socket, navigation or control. */
@RunWith(AndroidJUnit4::class)
class CpLaneRuntimeDeviceTest {
    @Test fun bothProfilesRunInBoundWorkerWithoutTouchingNavigation() = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val bitmap = Bitmap.createBitmap(640, 400, Bitmap.Config.ARGB_8888)
        bitmap.eraseColor(0xff808080.toInt())
        try {
            for (model in listOf("vlaneDay.mnn", "vlaneNight.mnn")) {
                CpLaneDetector(instrumentation.targetContext).use { detector ->
                    var executed = false
                    val deadline = SystemClock.elapsedRealtime() + 15_000
                    while (!executed && SystemClock.elapsedRealtime() < deadline) {
                        val result = detector.detect(bitmap, model)
                        executed = result != null || detector.status == "车道模型本帧未确认"
                        if (!executed) kotlinx.coroutines.delay(150)
                    }
                    instrumentation.sendStatus(0, Bundle().apply {
                        putString("lane_model", model); putBoolean("native_executed", executed)
                        putString("model_status", detector.status)
                    })
                    assertTrue("$model did not execute: ${detector.status}", executed)
                }
            }
        } finally { bitmap.recycle() }
    }
    @Test fun activateExplicitlyRequestedVisionSession() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        assertTrue(context.getSharedPreferences("phone_vision", android.content.Context.MODE_PRIVATE)
            .edit().putBoolean("cp_lane_enabled", true).commit())
        instrumentation.runOnMainSync {
            context.startActivity(android.content.Intent(context, PhoneVisionActivity::class.java)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        SystemClock.sleep(1000)
        instrumentation.runOnMainSync {
            context.startForegroundService(android.content.Intent(context, PhoneVisionService::class.java))
        }
        SystemClock.sleep(2000)
        assertTrue(context.getSharedPreferences("phone_vision", android.content.Context.MODE_PRIVATE)
            .getBoolean("cp_lane_enabled", false))
    }
}
