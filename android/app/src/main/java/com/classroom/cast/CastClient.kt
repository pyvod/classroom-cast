package com.classroom.cast

import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import okhttp3.MediaType.Companion.toMediaType
import okio.ByteString.Companion.toByteString
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

sealed class CastEvent {
    data class Connected(val serverInfo: JSONObject) : CastEvent()
    data class Error(val message: String) : CastEvent()
    data object Disconnected : CastEvent()
    data class Message(val text: String) : CastEvent()
}

class CastClient(private val host: String, private val port: Int, private val useSsl: Boolean = false) {

    // Auto-fix: iOS/Android apps use HTTP/WS, not HTTPS/WSS for streaming
    // If port is 8443 (HTTPS default), fall back to 8080 (HTTP default)
    private val actualPort = if (port == 8443) 8080 else port

    private val scheme get() = if (useSsl) "https" else "http"
    private val wsScheme get() = if (useSsl) "wss" else "ws"
    private val baseUrl get() = "$scheme://$host:$actualPort"

    private val client = buildClient()

    private var ws: WebSocket? = null
    private val _events = Channel<CastEvent>(Channel.BUFFERED)
    val events: Flow<CastEvent> = _events.receiveAsFlow()

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var pingJob: Job? = null
    private var reconnectJob: Job? = null
    private var isManuallyClosed = false

    private fun buildClient(): OkHttpClient {
        val builder = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS) // no read timeout for WS

        if (useSsl) {
            // Trust all certificates (self-signed cert on the classroom server)
            val trustAll = object : X509TrustManager {
                override fun checkClientTrusted(certs: Array<out X509Certificate>?, authType: String?) {}
                override fun checkServerTrusted(certs: Array<out X509Certificate>?, authType: String?) {}
                override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
            }
            try {
                val sslContext = SSLContext.getInstance("TLS")
                sslContext.init(null, arrayOf(trustAll), SecureRandom())
                builder.sslSocketFactory(sslContext.socketFactory, trustAll)
                builder.hostnameVerifier { _, _ -> true }
            } catch (_: Exception) {}
        }

        return builder.build()
    }

    fun connectWs() {
        isManuallyClosed = false
        startWs()
        startPing()
    }

    private fun startWs() {
        val url = "$wsScheme://$host:$actualPort/ws"
        val request = Request.Builder()
            .url(url)
            .build()

        client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                this@CastClient.ws = ws
            }

            override fun onMessage(ws: WebSocket, text: String) {
                if (text == "PONG") return  // Keepalive response, ignore
                _events.trySend(CastEvent.Message(text))
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                _events.trySend(CastEvent.Error(t.message ?: "WebSocket error"))
                scheduleReconnect()
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                _events.trySend(CastEvent.Disconnected)
                scheduleReconnect()
            }
        })
    }

    // MARK: - Keepalive PING every 10 seconds
    private fun startPing() {
        stopPing()
        pingJob = scope.launch {
            while (isActive) {
                delay(10_000)
                ws?.send("PING")
            }
        }
    }

    private fun stopPing() {
        pingJob?.cancel()
        pingJob = null
    }

    // MARK: - Auto-reconnect after 3 seconds
    private fun scheduleReconnect() {
        if (isManuallyClosed) return
        stopPing()
        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            delay(3_000)
            if (!isManuallyClosed) {
                startWs()
                startPing()
            }
        }
    }

    fun sendFrame(jpegData: ByteArray) {
        ws?.send(jpegData.toByteString())
    }

    fun sendCastStart() {
        ws?.send("CAST_START")
    }

    fun sendCastStop() {
        ws?.send("CAST_STOP")
    }

    fun closeWs() {
        isManuallyClosed = true
        stopPing()
        reconnectJob?.cancel()
        reconnectJob = null
        ws?.close(1000, "User stopped")
        ws = null
    }

    suspend fun fetchServerInfo(): JSONObject? {
        return try {
            withContext(Dispatchers.IO) {
                val request = Request.Builder()
                    .url("$baseUrl/api/info")
                    .build()
                val response = client.newCall(request).execute()
                JSONObject(response.body?.string() ?: return@withContext null)
            }
        } catch (e: Exception) {
            null
        }
    }

    suspend fun uploadPhoto(data: ByteArray, filename: String): Boolean {
        return try {
            withContext(Dispatchers.IO) {
                val body = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("photo", filename, data.toRequestBody("image/jpeg".toMediaType()))
                    .build()
                val request = Request.Builder()
                    .url("$baseUrl/api/upload")
                    .post(body)
                    .build()
                val response = client.newCall(request).execute()
                val json = JSONObject(response.body?.string() ?: "{}")
                json.optBoolean("ok", false)
            }
        } catch (e: Exception) {
            false
        }
    }

    suspend fun pushUrl(url: String): Boolean {
        return try {
            withContext(Dispatchers.IO) {
                val json = JSONObject().apply { put("url", url) }
                val body = json.toString().toRequestBody("application/json".toMediaType())
                val request = Request.Builder()
                    .url("$baseUrl/api/pushurl")
                    .post(body)
                    .build()
                val response = client.newCall(request).execute()
                val respJson = JSONObject(response.body?.string() ?: "{}")
                respJson.optBoolean("ok", false)
            }
        } catch (e: Exception) {
            false
        }
    }

    fun disconnect() {
        closeWs()
    }

    fun cleanup() {
        closeWs()
        scope.cancel()
    }
}
