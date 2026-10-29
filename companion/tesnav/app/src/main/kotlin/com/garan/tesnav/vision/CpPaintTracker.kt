package com.garan.tesnav.vision

import kotlin.math.abs

/** A visible uninterrupted fragment can be one dash. Require fresh observations
 * over 12m of motion before estimating solid; no elapsed-time-only confirmation.
 * This is a read-only experimental classifier, never actuation permission. */
internal class CpPaintTracker {
    private data class Track(var meters:Double=0.0,var frames:Int=0,var anchor:Float?=null,var color:String="unknown")
    private var tracks=arrayOf(Track(),Track())
    private var stream=""
    private var stamp=-1L
    private var speed:Double?=null
    fun clear() { tracks=arrayOf(Track(),Track());stream="";stamp=-1L;speed=null }

    fun update(input:CpPaintEstimate,source:String,captureNs:Long,egoSpeed:Double?):CpPaintEstimate {
        if(source.isBlank() || captureNs<=0) { clear();return CpPaintEstimate() }
        if(source==stream && captureNs<=stamp) { clear();return CpPaintEstimate() }
        val dt=if(source==stream && stamp>0) (captureNs-stamp)/1e9 else 0.0
        if(source!=stream || dt>.8) { tracks=arrayOf(Track(),Track());speed=null }
        val v=egoSpeed?.takeIf { it.isFinite() && it in 0.0..60.0 }
        val distance=if(dt in 0.0.. .8 && v!=null && speed!=null) (v+speed!!)*.5*dt else 0.0
        stream=source;stamp=captureNs;speed=v
        fun side(value:CpPaintSide,index:Int):CpPaintSide {
            if(value.type=="dashed") { tracks[index]=Track();return value }
            if(value.type!="continuous") { tracks[index]=Track();return value.copy(type="unknown") }
            var t=tracks[index]
            if((t.anchor!=null && value.boundaryX!=null && abs(t.anchor!!-value.boundaryX)>.04f) ||
                (t.color!="unknown" && value.color!="unknown" && t.color!=value.color)) {
                t=Track();tracks[index]=t
            }
            if(v==null) { tracks[index]=Track();return value.copy(type="unknown",reason="motionUnavailable") }
            if(t.frames>0)t.meters+=distance
            t.frames++;if(t.anchor==null)t.anchor=value.boundaryX;t.color=value.color
            return if(t.meters>=12 && t.frames>=5)value.copy(type="solid",reason="motionObserved")
                else value.copy(type="unknown",reason="needMotion")
        }
        return input.copy(left=side(input.left,0),right=side(input.right,1),controlEligible=false)
    }
}
