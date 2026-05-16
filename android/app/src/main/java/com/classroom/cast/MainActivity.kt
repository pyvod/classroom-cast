package com.classroom.cast

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.classroom.cast.ui.screens.CastScreen
import com.classroom.cast.ui.screens.HomeScreen
import com.classroom.cast.ui.screens.QrScannerScreen
import com.classroom.cast.ui.theme.ClassroomCastTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ClassroomCastTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF0D1117)
                ) {
                    AppNavigation()
                }
            }
        }
    }
}

@Composable
private fun AppNavigation() {
    var connectedClient by remember { mutableStateOf<CastClient?>(null) }
    var showScanner by remember { mutableStateOf(false) }

    // Preset values from QR scan
    var presetIp by remember { mutableStateOf<String?>(null) }
    var presetPort by remember { mutableStateOf<String?>(null) }
    var presetUseSsl by remember { mutableStateOf<Boolean?>(null) }

    when {
        connectedClient != null -> {
            CastScreen(
                client = connectedClient!!,
                onDisconnect = { connectedClient = null }
            )
        }
        showScanner -> {
            QrScannerScreen(
                onScanResult = { url ->
                    try {
                        val parsed = java.net.URI(url)
                        val host = parsed.host
                        val port = parsed.port
                        if (host != null) {
                            presetIp = host
                            presetPort = if (port > 0) port.toString() else "8080"
                            presetUseSsl = parsed.scheme == "https"
                        }
                    } catch (_: Exception) {}
                    showScanner = false
                },
                onBack = { showScanner = false }
            )
        }
        else -> {
            HomeScreen(
                presetIp = presetIp,
                presetPort = presetPort,
                presetUseSsl = presetUseSsl,
                onConnected = { client -> connectedClient = client },
                onScanClick = { showScanner = true }
            )
        }
    }
}
