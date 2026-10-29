package com.garan.tesnav.vision

import com.google.gson.Gson
import com.google.gson.JsonParser
import java.io.File
import javax.imageio.ImageIO
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test

/** Optional real-data check: raw user captures stay outside Git. Negative scenes
 * without paint must not inherit a type from the model's continuous boundary. */
class CpPaintPrivateReplayTest {
    @Test fun analysePrivateRoadRgbAndNativeMasks() {
        val location=System.getenv("CP_PAINT_REPLAY_DIR")
        assumeTrue("No private replay input configured",location!=null)
        val root=File(location!!)
        val rows=JsonParser.parseString(File(root,"outputs/results.json").readText()).asJsonArray
        val out=mutableListOf<Map<String,Any>>()
        for(row in rows) {
            val d=row.asJsonObject;val name=d["name"].asString
            require(name.matches(Regex("[A-Za-z0-9_-]{1,120}")))
            val source=name.substringAfter('-')
            val image=ImageIO.read(File(root,"inputs/$source.png"))
            val rgb=image.getRGB(0,0,image.width,image.height,null,0,image.width)
            val mask=CpRoadMaskCore.fromPacket(d["height"].asInt,d["width"].asInt,
                File(root,"outputs/$name.ids").readBytes(),File(root,"outputs/$name.confidence").readBytes())!!
            val estimate=CpPaintCore.estimate(rgb,image.width,image.height,mask)
            if(source.startsWith("day-wide")) {
                assertEquals("$name left no-paint street","unknown",estimate.left.type)
                assertEquals("$name right no-paint street","unknown",estimate.right.type)
            }
            assertFalse(estimate.controlEligible)
            out.add(mapOf("name" to name,"paint" to estimate))
        }
        File(root,"paint-results.json").writeText(Gson().toJson(out))
        assertEquals(18,out.size)
    }
}
