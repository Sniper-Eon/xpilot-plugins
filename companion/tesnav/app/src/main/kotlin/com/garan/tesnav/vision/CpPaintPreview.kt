package com.garan.tesnav.vision

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import kotlinx.coroutines.flow.MutableStateFlow
import android.app.AlertDialog
import android.content.Context
import android.graphics.BitmapFactory
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import com.google.gson.JsonParser
import java.io.File

/** Local phone presentation only. Never serialized in a C3 observation or CAN message. */
internal object CpPaintPreview {
    data class Frame(val estimate:CpPaintEstimate,val bitmap:Bitmap?,val issuedMs:Long,val expiresMs:Long,
        val frameId:Long,val model:String)
    val state=MutableStateFlow<Frame?>(null)
    @Volatile var renderImages=false
    fun remaining(age:Double?,elapsed:Long,wait:Double?):Long {
        if(age==null || !PhoneVisionBudget.canSubmit(age,elapsed,wait))return 0
        val credited=wait?.takeIf { it.isFinite() && it>=0 && it<=elapsed } ?: 0.0
        return (800-age-elapsed+credited).toLong().coerceIn(0,800)
    }
    fun clear() { state.value=null }
    fun expire(now:Long) { state.value?.let { if(now<it.issuedMs || now>=it.expiresMs)clear() } }
    fun fresh(frame:Frame?,now:Long):Frame?=frame?.takeIf { now>=it.issuedMs && now<it.expiresMs }
    fun text(estimate:CpPaintEstimate):String {
        fun side(s:CpPaintSide):String {
            val color=when(s.color) { "white"->"白色";"yellow"->"黄色";else->"" }
            val type=when(s.type) { "solid"->"实线";"dashed"->"虚线";"continuous"->"连续片段（待确认）"
                else->if(s.reason=="needMotion")"连续片段（待确认）" else "虚实未知" }
            return if(color.isEmpty() && type=="虚实未知")"未知" else color+type
        }
        return "手机标线估计 · 左：${side(estimate.left)} · 右：${side(estimate.right)}"
    }
    fun image(source:Bitmap,mask:CpRoadMask):Bitmap {
        val width=320;val height=(width.toFloat()*source.height/source.width).toInt().coerceAtLeast(1)
        val result=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888)
        val canvas=Canvas(result);val rect=Rect(0,0,width,height)
        canvas.drawBitmap(source,null,rect,Paint(Paint.FILTER_BITMAP_FLAG))
        val colors=intArrayOf(0,0x99ff3030.toInt(),0x9900ff40.toInt(),0x9940a0ff.toInt())
        val overlay=Bitmap.createBitmap(IntArray(mask.ids.size) { colors[mask.ids[it].toInt()] },
            mask.width,mask.height,Bitmap.Config.ARGB_8888)
        canvas.drawBitmap(overlay,null,rect,Paint())
        overlay.recycle();return result
    }
    /** Private offline evidence never enters the live state or C3 observation. */
    fun showReplay(context:Context):AlertDialog {
        val root=File(context.filesDir,"road-replay")
        try {
            val json=File(root,"outputs/results.json")
            require(json.length() in 1..131072)
            val rows=JsonParser.parseString(json.readText()).asJsonArray
            require(rows.size() in 1..64)
            val title=TextView(context)
            val view=ImageView(context).apply { adjustViewBounds=true }
            val layout=LinearLayout(context).apply { orientation=LinearLayout.VERTICAL;setPadding(24,24,24,24)
                addView(title);addView(view) }
            var index=0
            fun render() {
                val row=rows[index].asJsonObject;val name=row["name"].asString
                require(name.matches(Regex("[A-Za-z0-9_-]{1,120}")))
                val input=File(root,"inputs/${name.substringAfter('-')}.png")
                require(input.length() in 1..2_000_000)
                val options=BitmapFactory.Options().apply { inJustDecodeBounds=true }
                BitmapFactory.decodeFile(input.absolutePath,options)
                require(options.outWidth in 320..640 && options.outHeight in 200..480)
                val ids=File(root,"outputs/$name.ids");val confidence=File(root,"outputs/$name.confidence")
                require(ids.length() in 1..98304 && confidence.length()==ids.length())
                val mask=CpRoadMaskCore.fromPacket(row["height"].asInt,row["width"].asInt,ids.readBytes(),confidence.readBytes())!!
                val bitmap=BitmapFactory.decodeFile(input.absolutePath)!!
                try {
                    val pixels=IntArray(bitmap.width*bitmap.height)
                    bitmap.getPixels(pixels,0,bitmap.width,0,0,bitmap.width,bitmap.height)
                    title.text="离线回放 ${index+1}/${rows.size()} · $name\n"+
                        text(CpPaintCore.estimate(pixels,bitmap.width,bitmap.height,mask))+
                        "\n红绿蓝是通道调试色，不是标线颜色。单帧连续片段不确认为实线。"
                    view.setImageBitmap(image(bitmap,mask))
                } finally { bitmap.recycle() }
            }
            render()
            val dialog=AlertDialog.Builder(context).setTitle("只读模型回放").setView(layout)
                .setPositiveButton("下一张",null).setNegativeButton("关闭",null).create()
            dialog.setOnShowListener { dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                index=(index+1)%rows.size();runCatching { render() }.onFailure {
                    title.text="回放数据不可用";view.setImageDrawable(null)
                }
            } }
            dialog.show()
            return dialog
        } catch (_:Exception) {
            return AlertDialog.Builder(context).setMessage("尚无离线验证画面；实时标线估计可在有道路画面时使用。")
                .setPositiveButton("确定",null).show()
        }
    }
}
