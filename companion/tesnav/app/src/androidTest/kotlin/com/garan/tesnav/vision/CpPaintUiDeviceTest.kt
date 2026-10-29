package com.garan.tesnav.vision

import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.gson.JsonParser
import java.io.File
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Real UI acceptance. Offline replay cannot populate live state or a C3 packet;
 * a single continuous fragment stays unconfirmed. No route/vehicle command. */
@RunWith(AndroidJUnit4::class)
class CpPaintUiDeviceTest {
    @Test fun privateReplayUsesDebugLegendAndDoesNotConfirmSingleFrameSolid() {
        val i=InstrumentationRegistry.getInstrumentation();val context=i.targetContext
        val root=File(context.filesDir,"road-replay")
        assumeTrue(File(root,"outputs/results.json").exists())
        val activity=i.startActivitySync(Intent(context,PhoneVisionActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as PhoneVisionActivity
        var dialog:AlertDialog?=null
        try {
            i.runOnMainSync {
                activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                CpPaintPreview.clear()
                dialog=CpPaintPreview.showReplay(activity)
            }
            i.waitForIdleSync()
            val rows=JsonParser.parseString(File(root,"outputs/results.json").readText()).asJsonArray
            val target=rows.indexOfFirst { it.asJsonObject["name"].asString=="vlaneDay-night-lanes-20" }
            require(target>=0)
            i.runOnMainSync { repeat(target) { dialog!!.getButton(AlertDialog.BUTTON_POSITIVE).performClick() } }
            i.waitForIdleSync()
            fun texts(view:View):List<String> = (if(view is TextView)listOf(view.text.toString()) else emptyList())+
                (if(view is ViewGroup)(0 until view.childCount).flatMap { texts(view.getChildAt(it)) } else emptyList())
            lateinit var visible:String
            i.runOnMainSync { visible=texts(dialog!!.window!!.decorView).joinToString("\n") }
            assertTrue(visible.contains("离线回放"));assertTrue(visible.contains("连续片段"))
            assertFalse(Regex("手机标线估计[^\\n]*实线").containsMatchIn(visible))
            assertTrue(visible.contains("调试色"));assertNull(CpPaintPreview.state.value)
            val screenshot=i.uiAutomation.takeScreenshot()
            assertNotNull(screenshot)
            File(root,"outputs/paint-preview-ui.png").outputStream().use {
                screenshot!!.compress(Bitmap.CompressFormat.PNG,100,it)
            }
            screenshot?.recycle()
        } finally {
            i.runOnMainSync { dialog?.dismiss();activity.finish() }
        }
    }
    @Test fun activateOnlyExplicitlyRequestedReadOnlyPhoneFeature() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("activateReadOnlyPaint")=="true")
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val prefs=context.getSharedPreferences("phone_vision",android.content.Context.MODE_PRIVATE)
        val laneBefore=prefs.getBoolean("cp_lane_enabled",false)
        assertTrue(prefs.edit().putBoolean("cp_paint_enabled",true).commit())
        assertEquals(laneBefore,prefs.getBoolean("cp_lane_enabled",false))
        assertTrue(prefs.getBoolean("cp_paint_enabled",false))
    }
}
