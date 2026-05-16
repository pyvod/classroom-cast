package com.classroom.cast

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.withContext
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

    private val scheme get() = if (useSsl) "https" else "http"
    private val wsScheme get() = if (useSsl) "wss" else "ws"
    private val baseUrl get() = "$scheme://$host:$port"

    private val client = buildClient()

    private var ws: WebSocket? = null
    private val _events = Channel<CastEvent>(Channel.BUFFERED)
    val events: Flow<CastEvent> = _events.receiveAsFlow()

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
        val url = "$wsScheme://$host:$port/ws"
        val request = Request.Builder()
            .url(url)
            .build()

        client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                this@CastClient.ws = ws
            }

            override fun onMessage(ws: WebSocket, text: String) {
                _events.trySend(CastEvent.Message(text))
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                _events.trySend(CastEvent.Error(t.message ?: "WebSocket error"))
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                _events.trySend(CastEvent.Disconnected)
            }
        })
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
}
