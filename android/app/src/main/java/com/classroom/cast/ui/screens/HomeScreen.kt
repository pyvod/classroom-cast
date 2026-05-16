package com.classroom.cast.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.classroom.cast.CastClient
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    presetIp: String? = null,
    presetPort: String? = null,
    presetUseSsl: Boolean? = null,
    onConnected: (CastClient) -> Unit,
    onScanClick: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var ip by remember { mutableStateOf(presetIp ?: "") }
    var port by remember { mutableStateOf(presetPort ?: "8080") }
    var useSsl by remember { mutableStateOf(presetUseSsl ?: false) }
    var connecting by remember { mutableStateOf(false) }
    var errorMsg by remember { mutableStateOf<String?>(null) }

    // Apply preset when it changes (after QR scan)
    LaunchedEffect(presetIp, presetPort, presetUseSsl) {
        if (presetIp != null) ip = presetIp
        if (presetPort != null) port = presetPort
        if (presetUseSsl != null) useSsl = presetUseSsl
    }

    // Notification permission (Android 13+)
    val notifLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) {}
    LaunchedEffect(Unit) {
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D1117))
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(48.dp))

        // Logo area
        Box(
            modifier = Modifier
                .size(80.dp)
                .clip(CircleShape)
                .background(Color(0xFF1F6FEB)),
            contentAlignment = Alignment.Center
        ) {
            Text("投", fontSize = 32.sp, fontWeight = FontWeight.Bold, color = Color.White)
        }

        Spacer(Modifier.height(16.dp))
        Text("班级投屏", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Color(0xFFF0F6FC))
        Text("连接班级大屏", fontSize = 14.sp, color = Color(0xFF8B949E))
        Spacer(Modifier.height(32.dp))

        // Server connection card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF21262D)),
            border = CardDefaults.outlinedCardBorder().copy(
                brush = androidx.compose.ui.graphics.SolidColor(Color(0xFF30363D))
            )
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text("连接服务器", fontWeight = FontWeight.Bold, color = Color(0xFFF0F6FC))
                Spacer(Modifier.height(16.dp))

                OutlinedTextField(
                    value = ip,
                    onValueChange = { ip = it; errorMsg = null },
                    label = { Text("服务器 IP 地址") },
                    placeholder = { Text("例如 192.168.1.100") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Color(0xFF58A6FF),
                        unfocusedBorderColor = Color(0xFF30363D),
                        cursorColor = Color(0xFF58A6FF),
                        focusedLabelColor = Color(0xFF58A6FF),
                        unfocusedLabelColor = Color(0xFF8B949E),
                        focusedTextColor = Color(0xFFC9D1D9),
                        unfocusedTextColor = Color(0xFFC9D1D9),
                    ),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                )

                Spacer(Modifier.height(12.dp))

                OutlinedTextField(
                    value = port,
                    onValueChange = { port = it.filter { c -> c.isDigit() }; errorMsg = null },
                    label = { Text("端口") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Color(0xFF58A6FF),
                        unfocusedBorderColor = Color(0xFF30363D),
                        cursorColor = Color(0xFF58A6FF),
                        focusedLabelColor = Color(0xFF58A6FF),
                        unfocusedLabelColor = Color(0xFF8B949E),
                        focusedTextColor = Color(0xFFC9D1D9),
                        unfocusedTextColor = Color(0xFFC9D1D9),
                    ),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                )

                Spacer(Modifier.height(20.dp))

                // Scan QR button
                OutlinedButton(
                    onClick = onScanClick,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(44.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = Color(0xFF58A6FF)
                    ),
                    border = ButtonDefaults.outlinedButtonBorder.copy(
                        brush = androidx.compose.ui.graphics.SolidColor(Color(0xFF30363D))
                    )
                ) {
                    Text("📷 扫码识别服务器", fontSize = 14.sp, fontWeight = FontWeight.Medium)
                }

                Spacer(Modifier.height(12.dp))

                Button(
                    onClick = {
                        if (ip.isBlank()) {
                            errorMsg = "请输入服务器 IP 地址"
                            return@Button
                        }
                        connecting = true
                        errorMsg = null
                        scope.launch {
                            val portNum = port.toIntOrNull() ?: (if (useSsl) 8443 else 8080)
                            val client = CastClient(ip.trim(), portNum, useSsl = useSsl)
                            val info = client.fetchServerInfo()
                            if (info != null) {
                                client.connectWs()
                                onConnected(client)
                            } else {
                                errorMsg = "无法连接服务器，请检查 IP 和端口"
                                connecting = false
                            }
                        }
                    },
                    enabled = !connecting,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(50.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color(0xFF238636)
                    )
                ) {
                    Text(
                        if (connecting) "连接中..." else "连接",
                        fontSize = 16.sp, fontWeight = FontWeight.SemiBold
                    )
                }

                if (errorMsg != null) {
                    Spacer(Modifier.height(12.dp))
                    Text(
                        errorMsg!!,
                        color = Color(0xFFF85149),
                        fontSize = 13.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }
        }

        Spacer(Modifier.height(24.dp))

        // Instructions
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF161B22)),
            border = CardDefaults.outlinedCardBorder().copy(
                brush = androidx.compose.ui.graphics.SolidColor(Color(0xFF30363D))
            )
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("使用说明", fontWeight = FontWeight.Bold, color = Color(0xFFF0F6FC))
                Spacer(Modifier.height(8.dp))
                listOf(
                    "1. 确保手机连接了教室 WiFi",
                    "2. 点击「扫码识别」扫描大屏二维码",
                    "3. 或手动输入大屏上的 IP 和端口号",
                    "4. 点击「连接」开始使用"
                ).forEach { text ->
                    Text(text, color = Color(0xFF8B949E), fontSize = 13.sp, lineHeight = 22.sp)
                }
            }
        }
    }
}
