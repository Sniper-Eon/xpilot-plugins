package com.garan.tesnav.service

import android.os.SystemClock
import com.garan.tesnav.model.NavigationState
import com.google.gson.JsonParser
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/** Local phone observation reader. No C3 settings, vehicle commands or SDK setters. */
internal class TencentProbeClient(private val enabled:()->Boolean,private val publish:(NavigationState?)->Unit) {
    private val decoder=TencentProbeDecoder(android.os.Process.myUid()/100000)
    private val http=OkHttpClient.Builder().connectTimeout(300,TimeUnit.MILLISECONDS)
        .readTimeout(500,TimeUnit.MILLISECONDS).callTimeout(700,TimeUnit.MILLISECONDS).build()
    private var job:Job?=null
    @Volatile private var port:Int?=null
    fun reset(){decoder.reset();port=null}
    fun start(scope:CoroutineScope) {
        job=scope.launch(Dispatchers.IO) {
            while(isActive) {
                if(!enabled()){delay(300);continue}
                val ports=port?.let{listOf(it)} ?: (8898..8907).toList()
                var state:NavigationState?=null
                for(candidate in ports)try {
                    val request=Request.Builder().url("http://127.0.0.1:$candidate/navigation").build()
                    http.newCall(request).execute().use { response ->
                        require(response.isSuccessful)
                        val bytes=response.body?.byteStream()?.use { input ->
                            val output=java.io.ByteArrayOutputStream();val buffer=ByteArray(4096)
                            while(output.size()<=65536) {
                                val count=input.read(buffer,0,minOf(buffer.size,65537-output.size()))
                                if(count<0)break
                                output.write(buffer,0,count)
                            }
                            output.toByteArray()
                        } ?: error("missing body")
                        require(bytes.size<=65536)
                        val obj=JsonParser.parseString(bytes.toString(Charsets.UTF_8)).asJsonObject
                        require(obj.get("messageType")?.asString=="tencent_legacy_observations")
                        // Side processes have no live navigator. Do not pin to their empty UI singleton.
                        require(obj.getAsJsonObject("engineContext")?.get("navigatorPresent")?.asBoolean==true || port!=null)
                        state=decoder.decode(obj,SystemClock.elapsedRealtime(),System.currentTimeMillis());port=candidate
                    }
                    break
                }catch(_:Exception){ }
                if(state==null)port=null
                if(isActive && enabled())publish(state ?: NavigationState(navigationProvider=NavigationDataSource.TENCENT_API.name,
                    errorMessage="等待腾讯导航连接",navAssistSourceStatus="tencentDisconnected"))
                delay(200)
            }
        }
    }
    fun close(){job?.cancel();job=null;http.dispatcher.cancelAll()}
}
