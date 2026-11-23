package com.garan.tesnav.ui

import java.net.URLEncoder

/** Official routeplan URI for the installed legacy Tencent map. The address lookup
 * and map selection supply GCJ-02, also the default Tencent destination frame.
 * Never supply the C3/SDK's potentially stale fix as the route's starting point.
 */
internal object TencentMapDestination {
    fun uri(name: String, latitude: Double, longitude: Double, caller: String): String? {
        if (!latitude.isFinite() || latitude !in -90.0..90.0 ||
            !longitude.isFinite() || longitude !in -180.0..180.0 || caller.isBlank()) return null
        val values = linkedMapOf(
            "type" to "drive",
            "fromcoord" to "CurrentLocation",
            "to" to name.ifBlank { "地图选点" },
            "tocoord" to "$latitude,$longitude",
            // The installed legacy URI contract accepts the calling app identity.
            // Do not embed an example developer key or repurpose the AMap key.
            "referer" to caller,
        )
        return "qqmap://map/routeplan?" + values.entries.joinToString("&") {
            URLEncoder.encode(it.key, "UTF-8") + "=" + URLEncoder.encode(it.value, "UTF-8")
        }
    }
}
