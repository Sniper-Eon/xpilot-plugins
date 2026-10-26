package com.garan.tesnav.export

import com.garan.tesnav.model.GeoPoint
import com.garan.tesnav.model.NavigationMode
import com.garan.tesnav.model.NavigationState
import com.google.gson.JsonParser
import org.junit.Assert.*
import org.junit.Test
import kotlinx.coroutines.*
import java.util.concurrent.CopyOnWriteArrayList

/** Failure contracts: wrong revision, stale route, lost ACK, old host, oversized data,
 * bad coordinates, bend loss, cross-session chunks and navigation-loop blocking. */
class RouteGeometryTransferTest {
    private fun snapshot(revision: Long = 7, session: String = "test-route") =
        NavAssistV2Mapper.snapshot(NavigationState(navigationMode = NavigationMode.ROUTE_PLANNED,
            routeRevision = revision), session, 1, 1000, 1000)
    private fun route(revision: Long = 7) = SdkRouteGeometry(123, revision, 300,
        listOf(GeoPoint(31.0, 121.0), GeoPoint(31.001, 121.0), GeoPoint(31.001, 121.001)))

    @Test fun `encode preserves bend endpoints source indices and bound context`() {
        val result = RouteGeometryEncoder.prepare(route())
        val body = JsonParser.parseString(result.body.decodeToString()).asJsonObject
        assertEquals("gcj02", body["coordinateSystem"].asString)
        assertEquals(3, body["points"].asJsonArray.size())
        assertEquals("[0,1,2]", body["sourcePointIndices"].toString())
        assertTrue(body["toleranceMeters"].asDouble <= 5.0)
        assertEquals(64, result.routeId.length)
        assertTrue(result.chunks.all { it.size <= 2048 })
        assertArrayEquals(result.body, result.chunks.flatMap { it.toList() }.toByteArray())
    }
    @Test fun `invalid and unbounded routes fail without coarsening`() {
        for (bad in listOf(route().copy(points = listOf(GeoPoint(Double.NaN, 0.0), GeoPoint(0.0, 0.0))),
            route().copy(points = listOf(GeoPoint(91.0, 0.0), GeoPoint(0.0, 0.0))),
            route().copy(points = emptyList()), route().copy(points = List(50001) { GeoPoint(0.0, 0.0) }),
            route().copy(pathId = -1), route().copy(totalDistanceMeters = -1))) {
            assertTrue(runCatching { RouteGeometryEncoder.prepare(bad) }.isFailure)
        }
    }
    @Test fun `sender deduplicates route and resets on route end and session change`() = runBlocking {
        val packets = CopyOnWriteArrayList<String>()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val sender = RouteGeometryTransfer(scope, exchange = { _, packet ->
            val d = JsonParser.parseString(packet.decodeToString()).asJsonObject
            packets.add(d["sessionId"].asString + ":" + d["messageType"].asString)
            d.remove("payload"); d.remove("chunkCount")
            if (!d.has("chunkIndex")) d.addProperty("chunkIndex", -1)
            d.addProperty("messageType", "route_geometry_ack")
            d.addProperty("accepted", true)
            d.addProperty("complete", d["chunkIndex"].asInt >= 0)
            CanonicalJson.encode(d).toByteArray()
        })
        repeat(4) { sender.offer(snapshot(), "192.168.5.182", route()); delay(20) }
        delay(500); assertEquals(2, packets.size)
        sender.offer(snapshot(), "192.168.5.182", route())
        delay(30); assertEquals(2, packets.size)
        sender.offer(snapshot().copy(navigationMode = "idle"), "192.168.5.182", route())
        sender.offer(snapshot(session = "next"), "192.168.5.182", route())
        delay(400); assertEquals(4, packets.size)
        scope.cancel()
    }
    @Test fun `old host never receives chunks and invalid contexts send nothing`() = runBlocking {
        val packets = CopyOnWriteArrayList<String>()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val sender = RouteGeometryTransfer(scope, exchange = { _, p -> packets.add(p.decodeToString()); null })
        sender.offer(snapshot(), "8.8.8.8", route())
        sender.offer(snapshot(8), "192.168.5.182", route())
        delay(30); assertTrue(packets.isEmpty())
        sender.offer(snapshot(), "192.168.5.182", route())
        delay(700); assertEquals(3, packets.size)
        assertTrue(packets.all { it.contains("route_geometry_hello") })
        scope.cancel()
    }
}
