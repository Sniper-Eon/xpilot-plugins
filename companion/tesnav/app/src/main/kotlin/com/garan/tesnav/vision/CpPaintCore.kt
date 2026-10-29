package com.garan.tesnav.vision

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

internal data class CpPaintSide(val color:String="unknown",val type:String="unknown",
    val evidenceScore:Float=0f,val reason:String="insufficientEvidence",val paintRows:Int=0,val usableRows:Int=0,
    val boundaryX:Float?=null)
internal data class CpPaintEstimate(val left:CpPaintSide=CpPaintSide(),val right:CpPaintSide=CpPaintSide(),
    val source:String="phoneMnnBoundaryRgb",val experimental:Boolean=true,val controlEligible:Boolean=false)

/** Read-only image estimate guided by the observed left/right boundary channels.
 * The network's filled boundary itself never supplies solid/dashed or colour.
 * This initial C3-wide image region excludes the sky and the dashboard; it is
 * deliberately conservative and must not be promoted to crossing permission.
 */
internal object CpPaintCore {
    private data class Pixel(val r:Int,val g:Int,val b:Int) {
        val luminance:Double get()=.299*r+.587*g+.114*b
        val high:Int get()=max(r,max(g,b))
        val low:Int get()=min(r,min(g,b))
        fun color():String = when {
            high>=80 && low>=high*.78 -> "white"
            r>=100 && g>=85 && b<=min(r,g)*.55 && r.toDouble()/g in .90..1.35 -> "yellow"
            else -> "unknown"
        }
    }
    private fun pixel(rgb:IntArray,w:Int,x:Int,y:Int):Pixel {
        val p=rgb[y*w+x.coerceIn(0,w-1)]
        return Pixel((p ushr 16) and 255,(p ushr 8) and 255,p and 255)
    }
    fun estimate(rgb:IntArray,width:Int,height:Int,mask:CpRoadMask?):CpPaintEstimate {
        if(width !in 320..640 || height !in 200..480 || rgb.size!=width*height || mask==null ||
            CpRoadMaskCore.fromPacket(mask.height,mask.width,mask.ids,mask.confidence)==null)
            return CpPaintEstimate()
        return CpPaintEstimate(side(rgb,width,height,mask,1),side(rgb,width,height,mask,2))
    }
    private fun side(rgb:IntArray,w:Int,h:Int,mask:CpRoadMask,id:Int):CpPaintSide {
        // 0=qualified dark gap, 1=white, 2=yellow, 3=narrow bright stripe with
        // ambiguous colour, -1=ambiguous/occluded. Style and colour are separate.
        val rows=mutableListOf<Int>();val ys=mutableListOf<Int>();val centers=mutableListOf<Float>()
        for(my in 0 until mask.height) {
            val y=((my+.5)*h/mask.height).toInt().coerceIn(0,h-1)
            if(y<h*.40 || y>h*.66)continue
            val xs=(0 until mask.width).filter { x ->
                val i=my*mask.width+x
                mask.ids[i].toInt()==id && (mask.confidence[i].toInt() and 255)>=165
            }
            if(xs.isEmpty())continue
            val x=((xs.average()+.5)*w/mask.width).toInt()
            if(x<24 || x>=w-24)continue
            centers.add(x.toFloat()/w)
            val left=(-22..-13).map { pixel(rgb,w,x+it,y).luminance }.average()
            val right=(13..22).map { pixel(rgb,w,x+it,y).luminance }.average()
            if(min(left,right)<12 || max(left,right)>170 || abs(left-right)>45) {
                rows.add(-1);ys.add(y);continue
            }
            val threshold=max(left,right)*1.35+12
            val band=(-6..6).map { pixel(rgb,w,x+it,y) }
            val bright=band.map { it.luminance>threshold }
            // A broad white object/curb highlight is not a narrow paint stripe.
            val broad=bright.count { it }>9
            val votes=band.filter { it.luminance>threshold }.map { it.color() }
            val white=votes.count { it=="white" };val yellow=votes.count { it=="yellow" }
            val code=when {
                broad -> -1
                white>=2 && white>=yellow*2 -> 1
                yellow>=2 && yellow>=white*2 -> 2
                votes.size>=2 -> 3
                bright.none { it } -> 0
                else -> -1
            }
            rows.add(code);ys.add(y)
        }
        if(ys.size<16 || ys.last()-ys.first()<h*.12)return CpPaintSide(reason="shortBoundary")
        val usable=rows.count { it>=0 };val paint=rows.count { it>0 }
        if(usable<16 || usable<rows.size*.8 || paint<8)
            return CpPaintSide(reason="weakPaint",paintRows=paint,usableRows=usable)
        val white=rows.count { it==1 };val yellow=rows.count { it==2 }
        val color=if(max(white,yellow)<paint*.85)"unknown" else if(white>=yellow)"white" else "yellow"
        val runs=mutableListOf<Pair<Int,Int>>()
        for(v in rows) {
            val code=if(v>0)1 else v
            if(runs.isNotEmpty() && runs.last().first==code) {
                val last=runs.removeAt(runs.lastIndex);runs.add(code to last.second+1)
            } else runs.add(code to 1)
        }
        val ratio=paint.toDouble()/usable
        val internalGaps=runs.indices.filter { i -> i>0 && i<runs.lastIndex && runs[i].first==0 &&
            runs[i-1].first==1 && runs[i+1].first==1 && runs[i-1].second>=2 && runs[i+1].second>=2 }
        val type=when {
            ratio>=.90 && runs.none { it.first==0 && it.second>1 } -> "continuous"
            ratio in .25.. .85 && internalGaps.any { runs[it].second>=2 } -> "dashed"
            else -> "unknown"
        }
        return CpPaintSide(color,type,
            if(type=="unknown") .5f else min(.9,usable.toDouble()/rows.size*.9).toFloat(),
            if(type=="unknown")"patternAmbiguous" else "imageEstimate",paint,usable,centers.average().toFloat())
    }
}
