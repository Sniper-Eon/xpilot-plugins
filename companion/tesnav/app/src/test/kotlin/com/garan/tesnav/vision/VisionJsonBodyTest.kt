package com.garan.tesnav.vision

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.ResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.net.ServerSocket
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPOutputStream
import kotlin.concurrent.thread

class VisionJsonBodyTest {
    private fun unknown(bytes: ByteArray) = object : ResponseBody() {
        private val data = Buffer().write(bytes)
        override fun contentType() = null
        override fun contentLength() = -1L
        override fun source() = data
    }
    private fun compressed(bytes: ByteArray): ByteArray {
        val output = ByteArrayOutputStream()
        GZIPOutputStream(output).use { it.write(bytes) }
        return output.toByteArray()
    }
    private fun withGzip(bytes: ByteArray, action: (ResponseBody) -> Unit) {
        ServerSocket(0).use { server ->
            server.soTimeout = 4000
            val request = CompletableFuture<String>()
            val worker = thread(isDaemon = true) {
                try {
                    server.accept().use { socket ->
                        socket.soTimeout = 4000
                        val input = socket.getInputStream().bufferedReader()
                        val lines = mutableListOf<String>()
                        while (true) { val line = input.readLine() ?: break; if (line.isEmpty()) break; lines.add(line) }
                        request.complete(lines.joinToString("\n"))
                        val body = compressed(bytes)
                        val header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Encoding: gzip\r\nContent-Length: ${body.size}\r\nConnection: close\r\n\r\n"
                        socket.getOutputStream().apply { write(header.toByteArray()); write(body); flush() }
                    }
                } catch (e: Exception) { request.completeExceptionally(e) }
            }
            val client = OkHttpClient.Builder().callTimeout(4, TimeUnit.SECONDS).build()
            try {
                client.newCall(Request.Builder().url("http://127.0.0.1:${server.localPort}/v2/pair")
                    .header("X-Phone-Vision-Encoding", "gzip-v1").build()).execute().use { response ->
                    assertNull(response.header("Content-Encoding"))
                    val body = response.body!!
                    assertEquals(-1L, body.contentLength())
                    action(body)
                }
                val sent = request.get(4, TimeUnit.SECONDS).lowercase()
                assertTrue(sent.contains("accept-encoding: gzip"))
                assertTrue(sent.contains("x-phone-vision-encoding: gzip-v1"))
            } finally { client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown(); worker.join(4000) }
        }
    }
    @Test fun oldUncompressedBridgeStillWorksAtExactLimit() {
        "{\"frame\":7}".toResponseBody().use { assertEquals("{\"frame\":7}", readVisionJsonBody(it, 11)) }
    }
    @Test fun emptyAndKnownOversizedBodiesAreRejected() {
        "".toResponseBody().use { body -> assertThrows(IllegalStateException::class.java) { readVisionJsonBody(body, 10) } }
        "12345678901".toResponseBody().use { body -> assertThrows(IllegalStateException::class.java) { readVisionJsonBody(body, 10) } }
    }
    @Test fun unknownDecodedLengthIsBounded() {
        unknown("1234567890".toByteArray()).use { assertEquals("1234567890", readVisionJsonBody(it, 10)) }
        unknown("12345678901".toByteArray()).use { body -> assertThrows(IllegalStateException::class.java) { readVisionJsonBody(body, 10) } }
    }
    @Test fun transparentGzipSocketRoundTripPreservesJson() {
        val json = "{\"jpeg_b64\":\"" + "abcdef0123456789".repeat(4096) + "\"}"
        withGzip(json.toByteArray()) { assertEquals(json, readVisionJsonBody(it, 100_000)) }
    }
    @Test fun highlyCompressibleResponseCannotBypassDecodedLimit() {
        withGzip("a".repeat(200_000).toByteArray()) { body ->
            assertThrows(IllegalStateException::class.java) { readVisionJsonBody(body, 1024) }
        }
    }
}
