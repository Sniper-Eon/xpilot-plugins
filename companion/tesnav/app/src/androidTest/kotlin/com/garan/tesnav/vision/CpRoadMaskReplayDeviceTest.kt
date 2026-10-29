package com.garan.tesnav.vision

import android.graphics.BitmapFactory
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.gson.Gson
import java.io.File
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Offline native replay, in the bound worker. No C3 socket or vehicle command.
 * Failure cases: no road data when count heads reject; layout corruption;
 * unbounded buffers; malformed capture after a valid one reuses old evidence.
 */
@RunWith(AndroidJUnit4::class)
class CpRoadMaskReplayDeviceTest {
    @Test fun replayPrivateFramesWithBothProfiles() = runBlocking {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val root=File(context.filesDir,"road-replay")
        val frames=File(root,"inputs").listFiles()?.filter { it.extension=="png" }?.sortedBy { it.name } ?: emptyList()
        assertTrue("Provide private 640x400 PNG replay inputs",frames.size in 1..32)
        val output=File(root,"outputs").apply { mkdirs() }
        val rows=mutableListOf<Map<String,Any>>()
        for (model in listOf("vlaneDay.mnn","vlaneNight.mnn")) {
            CpLaneDetector(context).use { detector ->
                for (frame in frames) {
                    assertTrue(frame.length() in 1..2_000_000)
                    val bitmap=BitmapFactory.decodeFile(frame.absolutePath)!!
                    try {
                        assertEquals(640,bitmap.width);assertEquals(400,bitmap.height)
                        var result:CpLaneResult?=null
                        var road:CpRoadMask?=null
                        val end=SystemClock.elapsedRealtime()+15_000
                        var elapsed=0L
                        while(road==null && SystemClock.elapsedRealtime()<end) {
                            val start=SystemClock.elapsedRealtime()
                            result=detector.detect(bitmap,model,roadEnabled=true)
                            elapsed=SystemClock.elapsedRealtime()-start
                            road=detector.lastRoad
                            if(road==null) delay(200)
                        }
                        assertNotNull("$model/${frame.name}: ${detector.status}",road)
                        val mask=road!!
                        assertEquals("unmapped",mask.semantics);assertFalse(mask.controlEligible)
                        val prefix=model.removeSuffix(".mnn")+"-"+frame.nameWithoutExtension
                        File(output,"$prefix.ids").writeBytes(mask.ids)
                        File(output,"$prefix.confidence").writeBytes(mask.confidence)
                        rows.add(mapOf("name" to prefix,"width" to mask.width,"height" to mask.height,
                            "ms" to elapsed,"lane" to (result?.laneNumber ?: -1),
                            "histogram" to (0..3).map { c -> mask.ids.count { it.toInt()==c } },
                            "semantics" to mask.semantics,"controlEligible" to false))
                    } finally { bitmap.recycle() }
                }
            }
        }
        File(output,"results.json").writeText(Gson().toJson(rows))
    }
}
