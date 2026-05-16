package com.classroom.cast.ui.screens

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.core.content.FileProvider
import com.classroom.cast.CastClient
import com.classroom.cast.CastEvent
import com.classroom.cast.ScreenCastService
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CastScreen(
    client: CastClient,
    onDisconnect: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var selectedTab by remember { mutableStateOf(0) }
    var statusText by remember { mutableStateOf("已连接服务器") }
    var isCasting by remember { mutableStateOf(false) }
    var isStreamActive by remember { mutableStateOf(false) }
    var isCameraActive by remember { mutableStateOf(false) }
    var urlInput by remember { mutableStateOf("") }
    var photoUri by remember { mutableStateOf<Uri?>(null) }

    // Screen capture permission launcher
    val screenCaptureLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            ScreenCastService.start(context, result.resultCode, result.data!!, client)
            isCasting = true
            isStreamActive = true
            statusText = "屏幕镜像已开始"
            client.sendCastStart()
        } else {
            statusText = "屏幕共享权限被拒绝"
        }
    }

    // Camera capture launcher
    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        if (success && photoUri != null) {
            scope.launch {
                statusText = "上传中..."
                try {
                    val stream = context.contentResolver.openInputStream(photoUri!!)
                    val bytes = stream?.readBytes()
                    stream?.close()
                    if (bytes != null) {
                        val filename = "photo_${System.currentTimeMillis()}.jpg"
                        val ok = client.uploadPhoto(bytes, filename)
                        statusText = if (ok) "✅ 照片已发送" else "❌ 发送失败"
                    }
                } catch (e: Exception) {
                    statusText = "❌ 发送失败: ${e.message}"
                }
            }
        }
    }

    // Photo pick launcher
    val pickPhotoLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            scope.launch {
                statusText = "上传中..."
                try {
                    val stream = context.contentResolver.openInputStream(uri)
                    val bytes = stream?.readBytes()
                    stream?.close()
                    if (bytes != null) {
                        val filename = "photo_${System.currentTimeMillis()}.jpg"
                        val ok = client.uploadPhoto(bytes, filename)
                        statusText = if (ok) "✅ 照片已发送" else "❌ 发送失败"
                    }
                } catch (e: Exception) {
                    statusText = "❌ 发送失败: ${e.message}"
                }
            }
        }
    }

    // Collect WebSocket events
    LaunchedEffect(client) {
        client.events.collectLatest { event ->
            when (event) {
                is CastEvent.Error -> {
                    statusText = "连接错误: ${event.message}"
                    isCasting = false
                    isStreamActive = false
                }
                is CastEvent.Disconnected -> {
                    statusText = "与服务器断开连接"
                    isCasting = false
                    isStreamActive = false
                }
                is CastEvent.Message -> {
                    if (event.text == "CLIENT_DISCONNECT") {
                        statusText = "大屏端已断开连接"
                        isCasting = false
                        isStreamActive = false
                        ScreenCastService.stop(context)
                    }
                }
                else -> {}
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D1117))
            .verticalScroll(rememberScrollState())
    ) {
        // Top bar
        Surface(
            color = Color(0xFF161B22),
            shadowElevation = 2.dp
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .statusBarsPadding()
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "班级投屏",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp,
                    color = Color(0xFFF0F6FC)
                )
                Spacer(Modifier.weight(1f))
                val anyActive = isCasting || isCameraActive
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(if (anyActive) Color(0xFF3FB950) else Color(0xFF8B949E))
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    if (anyActive) "投屏中" else "已连接",
                    color = if (anyActive) Color(0xFF3FB950) else Color(0xFF8B949E),
                    fontSize = 13.sp
                )
            }
        }

        // Tab selector
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp)
                .background(Color(0xFF21262D), RoundedCornerShape(12.dp))
                .padding(4.dp)
        ) {
            listOf("屏幕镜像", "实物展台", "拍照上传", "推送网址").forEachIndexed { i, label ->
                val selected = selectedTab == i
                Text(
                    label,
                    modifier = Modifier
                        .weight(1f)
                        .clickable { selectedTab = i }
                        .background(
                            if (selected) Color(0xFF1F6FEB) else Color.Transparent,
                            RoundedCornerShape(10.dp)
                        )
                        .padding(vertical = 12.dp),
                    textAlign = TextAlign.Center,
                    color = if (selected) Color.White else Color(0xFF8B949E),
                    fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                    fontSize = 14.sp
                )
            }
        }

        // Status bar
        Text(
            statusText,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            color = Color(0xFF8B949E),
            fontSize = 13.sp,
            textAlign = TextAlign.Center
        )

        // Content based on tab
        when (selectedTab) {
            0 -> ScreenMirrorTab(
                isActive = isStreamActive,
                onStart = {
                    val mgr = context.getSystemService(MediaProjectionManager::class.java)
                    screenCaptureLauncher.launch(mgr.createScreenCaptureIntent())
                },
                onStop = {
                    isCasting = false
                    isStreamActive = false
                    ScreenCastService.stop(context)
                    client.sendCastStop()
                    statusText = "投屏已停止"
                }
            )
            1 -> DocumentCameraTab(
                client = client,
                scope = scope,
                onStatusChange = { status ->
                    statusText = status
                    if (status.contains("已开启")) {
                        isCameraActive = true
                        isCasting = true
                    } else if (status.contains("已停止")) {
                        isCameraActive = false
                        isCasting = isStreamActive
                    }
                },
            )
            2 -> PhotoUploadTab(
                onTakePhoto = {
                    val file = File(context.cacheDir, "capture_${System.currentTimeMillis()}.jpg")
                    photoUri = FileProvider.getUriForFile(
                        context, "${context.packageName}.fileprovider", file
                    )
                    try {
                        cameraLauncher.launch(photoUri)
                    } catch (e: Exception) {
                        statusText = "无法启动相机: ${e.message}"
                    }
                },
                onPickPhoto = {
                    pickPhotoLauncher.launch("image/*")
                }
            )
            3 -> UrlPushTab(
                url = urlInput,
                onUrlChange = { urlInput = it },
                onPush = {
                    scope.launch {
                        val pushUrl = urlInput.trim()
                        if (pushUrl.isBlank()) {
                            statusText = "请输入网址"
                            return@launch
                        }
                        val finalUrl = if (!pushUrl.startsWith("http://") && !pushUrl.startsWith("https://"))
                            "https://$pushUrl" else pushUrl
                        statusText = "推送中..."
                        val ok = client.pushUrl(finalUrl)
                        statusText = if (ok) "✅ 网址已推送到大屏" else "❌ 推送失败"
                        if (ok) urlInput = ""
                    }
                }
            )
        }

        Spacer(Modifier.height(16.dp))

        // Disconnect button
        Button(
            onClick = {
                ScreenCastService.stop(context)
                client.sendCastStop()
                client.disconnect()
                onDisconnect()
            },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .height(48.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF21262D))
        ) {
            Text("断开连接", color = Color(0xFFF85149), fontWeight = FontWeight.SemiBold)
        }

        Spacer(Modifier.height(24.dp))
    }
}

// --------------- Screen Mirror Tab ---------------

@Composable
private fun ScreenMirrorTab(
    isActive: Boolean,
    onStart: () -> Unit,
    onStop: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF21262D))
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("📲", fontSize = 48.sp)
            Spacer(Modifier.height(12.dp))
            Text(
                "屏幕镜像",
                fontWeight = FontWeight.Bold,
                color = Color(0xFFF0F6FC),
                fontSize = 18.sp
            )
            Text(
                "将手机屏幕实时投射到大屏",
                color = Color(0xFF8B949E),
                fontSize = 13.sp
            )
            Spacer(Modifier.height(20.dp))

            if (isActive) {
                Button(
                    onClick = onStop,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDA3633))
                ) {
                    Text("停止投屏", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                }
            } else {
                Button(
                    onClick = onStart,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF238636))
                ) {
                    Text("开始投屏", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                }
            }
        }
    }
}

// --------------- Photo Upload Tab ---------------

@Composable
private fun PhotoUploadTab(
    onTakePhoto: () -> Unit,
    onPickPhoto: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF21262D))
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("📷", fontSize = 48.sp)
            Spacer(Modifier.height(12.dp))
            Text(
                "拍照上传",
                fontWeight = FontWeight.Bold,
                color = Color(0xFFF0F6FC),
                fontSize = 18.sp
            )
            Text(
                "拍照或选择照片，发送到大屏显示",
                color = Color(0xFF8B949E),
                fontSize = 13.sp
            )
            Spacer(Modifier.height(20.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Button(
                    onClick = onTakePhoto,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1F6FEB))
                ) {
                    Text("拍照", fontWeight = FontWeight.SemiBold)
                }
                OutlinedButton(
                    onClick = onPickPhoto,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFC9D1D9))
                ) {
                    Text("选择照片", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

// --------------- URL Push Tab ---------------

@Composable
private fun UrlPushTab(
    url: String,
    onUrlChange: (String) -> Unit,
    onPush: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF21262D))
    ) {
        Column(
            modifier = Modifier.padding(20.dp)
        ) {
            Text("🌐", fontSize = 48.sp)
            Spacer(Modifier.height(12.dp))
            Text(
                "网址推送",
                fontWeight = FontWeight.Bold,
                color = Color(0xFFF0F6FC),
                fontSize = 18.sp
            )
            Text(
                "输入网址，大屏自动打开浏览器",
                color = Color(0xFF8B949E),
                fontSize = 13.sp
            )
            Spacer(Modifier.height(16.dp))

            OutlinedTextField(
                value = url,
                onValueChange = onUrlChange,
                placeholder = { Text("输入网址") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF58A6FF),
                    unfocusedBorderColor = Color(0xFF30363D),
                    cursorColor = Color(0xFF58A6FF),
                    focusedTextColor = Color(0xFFC9D1D9),
                    unfocusedTextColor = Color(0xFFC9D1D9),
                ),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri)
            )

            Spacer(Modifier.height(16.dp))

            Button(
                onClick = onPush,
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1F6FEB))
            ) {
                Text("推送到大屏", fontWeight = FontWeight.SemiBold)
            }
        }
    }
}
