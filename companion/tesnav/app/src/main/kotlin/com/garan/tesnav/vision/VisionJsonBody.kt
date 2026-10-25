package com.garan.tesnav.vision

import okhttp3.ResponseBody
import java.io.ByteArrayOutputStream

/** OkHttp's transparent gzip has unknown decoded length; bound the decoded stream. */
internal fun readVisionJsonBody(body: ResponseBody, limit: Int): String {
    require(limit in 1..3_000_000)
    val declared = body.contentLength()
    check(declared == -1L || declared in 1..limit.toLong()) { "画面大小异常" }
    val output = ByteArrayOutputStream(minOf(limit, 8192))
    val buffer = ByteArray(8192)
    body.byteStream().use { input ->
        while (true) {
            val count = input.read(buffer, 0, minOf(buffer.size, limit - output.size() + 1))
            if (count == -1) break
            check(output.size() + count <= limit) { "画面大小异常" }
            output.write(buffer, 0, count)
        }
    }
    check(output.size() > 0) { "画面为空" }
    return output.toString(Charsets.UTF_8.name())
}
