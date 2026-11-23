package com.garan.tesnav.ui

import java.net.URI
import java.net.URLDecoder
import org.junit.Assert.*
import org.junit.Test

/** Failures: swapped axes; unescaped place names; invalid target launches home;
 * locale commas corrupt coordinates; selecting Tencent blocks idle searches.
 * Dispatch means a route page request, never a navigation/control acknowledgement.
 */
class TencentMapDestinationTest {
    private fun fields(uri: String): Map<String, String> = URI(uri).rawQuery.split("&").associate {
        val pair = it.split("=", limit = 2)
        URLDecoder.decode(pair[0], "UTF-8") to URLDecoder.decode(pair[1], "UTF-8")
    }

    @Test fun `hands off GCJ destination latitude first with independent current origin`() {
        val uri = TencentMapDestination.uri("堤田市场 & A+B #入口", 23.012345, 113.123456,
            "com.garan.tesnav.tenengkai.lane")!!
        assertEquals("qqmap", URI(uri).scheme)
        assertEquals("map", URI(uri).host)
        assertEquals("/routeplan", URI(uri).path)
        val p = fields(uri)
        assertEquals("drive", p["type"])
        assertEquals("CurrentLocation", p["fromcoord"])
        assertEquals("23.012345,113.123456", p["tocoord"])
        assertEquals("堤田市场 & A+B #入口", p["to"])
        assertEquals("com.garan.tesnav.tenengkai.lane", p["referer"])
        assertEquals(5, p.size)
    }

    @Test fun `invalid coordinates or missing caller cannot produce a launch`() {
        for ((lat, lon) in listOf(Double.NaN to 113.0, 23.0 to Double.POSITIVE_INFINITY,
            91.0 to 113.0, 23.0 to -181.0)) {
            assertNull(TencentMapDestination.uri("地点", lat, lon, "xpilot"))
        }
        assertNull(TencentMapDestination.uri("地点", 23.0, 113.0, " "))
    }

    @Test fun `coordinates are locale independent and blank name has meaningful fallback`() {
        val saved = java.util.Locale.getDefault()
        try {
            java.util.Locale.setDefault(java.util.Locale.GERMANY)
            val p = fields(TencentMapDestination.uri(" ", 23.5, 113.25, "xpilot")!!)
            assertEquals("23.5,113.25", p["tocoord"])
            assertEquals("地图选点", p["to"])
        } finally { java.util.Locale.setDefault(saved) }
    }
}
