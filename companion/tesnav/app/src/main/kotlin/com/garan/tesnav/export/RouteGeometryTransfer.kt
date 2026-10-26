package com.garan.tesnav.export

import com.garan.tesnav.model.GeoPoint
import com.garan.tesnav.util.RouteGeometrySimplifier
import com.google.gson.Strictness
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import java.io.StringReader
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.security.MessageDigest
import java.util.Base64
import kotlinx.coroutines.*

/** Captured SDK path, never an inferred driven trace or a hidden alternate route. */
internal data class SdkRouteGeometry(
    val pathId: Long, val routeRevision: Long, val totalDistanceMeters: Int, val points: List<GeoPoint>,
)
internal data class PreparedRouteGeometry(val body: ByteArray, val routeId: String, val chunks: List<ByteArray>)

internal object RouteGeometryEncoder {
    fun prepare(route: SdkRouteGeometry): PreparedRouteGeometry {
        require(route.pathId >= 0 && route.routeRevision >= 0 && route.totalDistanceMeters in 0..30_000_000)
        require(route.points.size in 2..50_000)
        require(route.points.all { it.latitude.isFinite() && it.longitude.isFinite() &&
            it.latitude in -90.0..90.0 && it.longitude in -180.0..180.0 })
        val simplified = RouteGeometrySimplifier.simplifyForViewport(route.points,
            viewportWidthPixels = 1024.0, viewportHeightPixels = 1024.0, maxToleranceMeters = 5.0)
        require(simplified.points.size in 2..4096)
        var cursor = 0
        val indices = simplified.points.map { kept ->
            while (cursor < route.points.size && route.points[cursor] !== kept) cursor++
            require(cursor < route.points.size)
            cursor++
            cursor - 1
        }
        val body = CanonicalJson.encode(linkedMapOf(
            "schemaVersion" to 1, "coordinateSystem" to "gcj02", "pathId" to route.pathId,
            "sourcePointCount" to route.points.size, "sourcePointIndices" to indices,
            "totalDistanceMeters" to route.totalDistanceMeters, "toleranceMeters" to simplified.toleranceMeters,
            "points" to simplified.points.map { listOf(it.latitude, it.longitude) },
        )).toByteArray(Charsets.UTF_8)
        require(body.size <= 128 * 1024)
        val chunks = body.asList().chunked(2048).map { it.toByteArray() }
        require(chunks.size in 1..64)
        val digest = MessageDigest.getInstance("SHA-256").digest(body).joinToString("") { "%02x".format(it) }
        return PreparedRouteGeometry(body, digest, chunks)
    }
}

/** Independent low-rate IO. A failed/old geometry peer never changes navigation delivery state. */
internal class RouteGeometryTransfer(
    private val scope: CoroutineScope,
    private val clockMs: () -> Long = { System.nanoTime() / 1_000_000 },
    private val exchange: (String, ByteArray) -> ByteArray? = ::geometryDatagram,
) {
    private data class Key(val host: String, val session: String, val revision: Long, val pathId: Long)
    private var key: Key? = null
    private var job: Job? = null
    private var lastAttempt = Long.MIN_VALUE
    private var cachedRoute: SdkRouteGeometry? = null
    private var cached: PreparedRouteGeometry? = null
    @Volatile private var lastOfferMs = 0L

    @Synchronized fun clear() {
        key = null
        job?.cancel()
        job = null
        cachedRoute = null
        cached = null
    }

    @Synchronized fun offer(snapshot: NavAssistV2Snapshot, host: String, route: SdkRouteGeometry?) {
        if (route == null || snapshot.navigationMode !in setOf("route_planned", "realtime", "simulation") ||
            snapshot.coordinateSystem != "gcj02" || snapshot.routeRevision != route.routeRevision || !privateIpv4(host)) {
            clear(); return
        }
        val next = Key(host, snapshot.sessionId, snapshot.routeRevision, route.pathId)
        val now = clockMs()
        lastOfferMs = now
        if (key == next && (job?.isActive == true || now - lastAttempt < 10_000)) return
        job?.cancel()
        key = next
        lastAttempt = now
        job = scope.launch {
            withTimeoutOrNull(12_000) {
            try {
                val prepared = synchronized(this@RouteGeometryTransfer) {
                    if (cachedRoute !== route) {
                        cached = null
                        cachedRoute = route
                    }
                    cached
                } ?: RouteGeometryEncoder.prepare(route).also {
                    synchronized(this@RouteGeometryTransfer) { if (key == next) cached = it }
                }
                suspend fun ask(index: Int): Boolean? {
                    val packet = linkedMapOf<String, Any>("messageType" to
                        if (index < 0) "route_geometry_hello" else "route_geometry_chunk",
                        "schemaVersion" to 1, "sessionId" to next.session,
                        "routeRevision" to next.revision, "routeId" to prepared.routeId)
                    if (index >= 0) {
                        packet["chunkIndex"] = index
                        packet["chunkCount"] = prepared.chunks.size
                        packet["payload"] = Base64.getEncoder().encodeToString(prepared.chunks[index])
                    }
                    val bytes = CanonicalJson.encode(packet).toByteArray(Charsets.UTF_8)
                    repeat(3) {
                        currentCoroutineContext().ensureActive()
                        if (clockMs() - lastOfferMs > 1200 || synchronized(this@RouteGeometryTransfer) { key != next }) return null
                        val reply = exchange(next.host, bytes)
                        currentCoroutineContext().ensureActive()
                        // At most ~6 packets/s, independent from the ordinary snapshot loop.
                        delay(160)
                        val complete = reply?.let { parseGeometryAck(it, next.session, next.revision, prepared.routeId, index) }
                        if (complete != null) return complete
                    }
                    return null
                }
                val complete = ask(-1) ?: return@withTimeoutOrNull
                if (!complete) {
                    for (index in prepared.chunks.indices) {
                        val done = ask(index) ?: return@withTimeoutOrNull
                        if (done) return@withTimeoutOrNull
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                // Invalid/overlarge route or unavailable peer affects this optional data path only.
            }
            }
        }
    }
}

internal fun privateIpv4(host: String): Boolean {
    val parts = host.split('.')
    if (parts.size != 4 || parts.any { it.isEmpty() || it.any { c -> c !in '0'..'9' } || it.length > 3 }) return false
    val p = parts.map { it.toIntOrNull() ?: return false }
    return p.all { it in 0..255 } && (p[0] == 10 || p[0] == 172 && p[1] in 16..31 || p[0] == 192 && p[1] == 168)
}

private fun geometryDatagram(host: String, bytes: ByteArray): ByteArray? = runCatching {
    require(privateIpv4(host) && bytes.size <= 4096)
    DatagramSocket().use { socket ->
        socket.soTimeout = 300
        socket.connect(InetAddress.getByName(host), 4213)
        socket.send(DatagramPacket(bytes, bytes.size))
        val packet = DatagramPacket(ByteArray(1025), 1025)
        socket.receive(packet)
        require(packet.length <= 1024)
        packet.data.copyOf(packet.length)
    }
}.getOrNull()

internal fun parseGeometryAck(bytes: ByteArray, session: String, revision: Long, routeId: String, index: Int): Boolean? = runCatching {
    require(bytes.size in 1..1024)
    val fields = mutableMapOf<String, Any>()
    JsonReader(StringReader(bytes.decodeToString(throwOnInvalidSequence = true))).use { reader ->
        reader.strictness = Strictness.STRICT
        reader.beginObject()
        while (reader.hasNext()) {
            val name = reader.nextName()
            require(!fields.containsKey(name))
            fields[name] = when (reader.peek()) {
                JsonToken.STRING -> reader.nextString()
                JsonToken.BOOLEAN -> reader.nextBoolean()
                JsonToken.NUMBER -> reader.nextString().also { require(it.matches(Regex("-?(0|[1-9][0-9]*)"))) }.toLong()
                else -> error("bad ack")
            }
        }
        reader.endObject()
        require(reader.peek() == JsonToken.END_DOCUMENT)
    }
    require(fields.keys == setOf("messageType", "schemaVersion", "sessionId", "routeRevision", "routeId", "chunkIndex", "accepted", "complete"))
    require(fields["messageType"] == "route_geometry_ack" && fields["schemaVersion"] == 1L &&
        fields["sessionId"] == session && fields["routeRevision"] == revision && fields["routeId"] == routeId &&
        fields["chunkIndex"] == index.toLong() && fields["accepted"] == true)
    fields["complete"] as Boolean
}.getOrNull()
