package com.classroom.cast.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.util.Size
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.classroom.cast.CastClient
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

@Composable
fun DocumentCameraTab(
    client: CastClient,
    scope: kotlinx.coroutines.CoroutineScope,
    onStatusChange: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var hasCameraPermission by remember { mutableStateOf(false) }
    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    val isStreaming = remember { AtomicBoolean(false) }
    val lastFrameMs = remember { AtomicLong(0L) }
    val imageCaptureRef = remember { mutableStateOf<ImageCapture?>(null) }
    val cameraProviderRef = remember { mutableStateOf<ProcessCameraProvider?>(null) }

    // Compose state for UI recomposition
    var streamingState by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasCameraPermission = granted
    }

    LaunchedEffect(Unit) {
        hasCameraPermission = ContextCompat.checkSelfPermission(
            context, Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        if (!hasCameraPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    // Cleanup camera when leaving this composable
    DisposableEffect(Unit) {
        onDispose {
            isStreaming.set(false)
            cameraProviderRef.value?.unbindAll()
            cameraExecutor.shutdown()
        }
    }

    Card(
        modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF21262D))
    ) {
        if (hasCameraPermission) {
            Column(
                modifier = Modifier.padding(20.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("📷", fontSize = 48.sp)
                Spacer(Modifier.height(8.dp))
                Text(
                    "实物展台",
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFFF0F6FC),
                    fontSize = 18.sp
                )
                Text(
                    "用手机摄像头拍摄课本/试卷，实时显示在大屏上",
                    color = Color(0xFF8B949E),
                    fontSize = 13.sp
                )
                Spacer(Modifier.height(16.dp))

                // Camera preview
                AndroidView(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(280.dp)
                        .background(Color.Black, RoundedCornerShape(12.dp)),
                    factory = { ctx ->
                        val previewView = PreviewView(ctx)
                        val cameraProviderFuture = ProcessCameraProvider.getInstance(ctx)

                        cameraProviderFuture.addListener({
                            val provider = cameraProviderFuture.get()
                            cameraProviderRef.value = provider

                            val preview = Preview.Builder().build().also {
                                it.setSurfaceProvider(previewView.surfaceProvider)
                            }

                            // ImageAnalysis: captures frames for live streaming
                            val imageAnalysis = ImageAnalysis.Builder()
                                .setTargetResolution(Size(1280, 720))
                                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                                .build()

                            imageAnalysis.setAnalyzer(cameraExecutor) { proxy ->
                                if (isStreaming.get() && proxy.image != null) {
                                    val now = System.currentTimeMillis()
                                    if (now - lastFrameMs.get() >= 150) {
                                        lastFrameMs.set(now)
                                        try {
                                            val jpeg = yuv420ToJpeg(proxy, 55)
                                            client.sendFrame(jpeg)
                                        } catch (_: Exception) {}
                                    }
                                }
                                proxy.close()
                            }

                            // ImageCapture: for high-quality still photo capture
                            val imageCapture = ImageCapture.Builder()
                                .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
                                .build()
                            imageCaptureRef.value = imageCapture

                            provider.unbindAll()
                            provider.bindToLifecycle(
                                lifecycleOwner,
                                CameraSelector.DEFAULT_BACK_CAMERA,
                                preview,
                                imageAnalysis,
                                imageCapture,
                            )
                        }, ContextCompat.getMainExecutor(ctx))

                        previewView
                    }
                )

                Spacer(Modifier.height(16.dp))

                // Control buttons
                if (streamingState) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        // Capture still photo button
                        Button(
                            onClick = {
                                val capture = imageCaptureRef.value
                                if (capture == null) return@Button
                                capture.takePicture(
                                    cameraExecutor,
                                    object : ImageCapture.OnImageCapturedCallback() {
                                        override fun onCaptureSuccess(image: ImageProxy) {
                                            try {
                                                val jpeg = yuv420ToJpeg(image, 85)
                                                val filename =
                                                    "camera_${System.currentTimeMillis()}.jpg"
                                                scope.launch {
                                                    val ok = client.uploadPhoto(jpeg, filename)
                                                    if (ok) {
                                                        onStatusChange("✅ 照片已发送到⼤屏")
                                                    } else {
                                                        onStatusChange("❌ 发送失败")
                                                    }
                                                }
                                            } catch (e: Exception) {
                                                onStatusChange("拍照失败: ${e.message}")
                                            }
                                            image.close()
                                        }

                                        override fun onError(e: ImageCaptureException) {
                                            onStatusChange("拍照失败: ${e.message}")
                                        }
                                    }
                                )
                            },
                            modifier = Modifier.weight(1f).height(50.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Color(0xFF1F6FEB)
                            )
                        ) {
                            Text("📸 拍照", fontWeight = FontWeight.SemiBold)
                        }

                        // Stop streaming button
                        Button(
                            onClick = {
                                isStreaming.set(false)
                                streamingState = false
                                client.sendCastStop()
                                onStatusChange("实物展台已停止")
                            },
                            modifier = Modifier.weight(1f).height(50.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Color(0xFFDA3633)
                            )
                        ) {
                            Text("停止", fontWeight = FontWeight.SemiBold)
                        }
                    }
                } else {
                    // Start streaming button
                    Button(
                        onClick = {
                            isStreaming.set(true)
                            streamingState = true
                            client.sendCastStart()
                            onStatusChange("实物展台已开启")
                        },
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFF238636)
                        )
                    ) {
                        Text(
                            "📷 开启实物展台",
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 16.sp
                        )
                    }
                }
            }
        } else {
            // No camera permission: show request UI
            Column(
                modifier = Modifier.padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    "需要相机权限才能使用实物展台",
                    color = Color(0xFF8B949E),
                    fontSize = 14.sp
                )
                Spacer(Modifier.height(12.dp))
                Button(onClick = {
                    permissionLauncher.launch(Manifest.permission.CAMERA)
                }) {
                    Text("授予权限")
                }
                Spacer(Modifier.height(8.dp))
                TextButton(onClick = {
                    onStatusChange("需要相机权限")
                }) {
                    Text("返回", color = Color(0xFF8B949E))
                }
            }
        }
    }
}

/**
 * Convert CameraX ImageProxy (YUV_420_888 or JPEG) to JPEG byte array.
 *
 * - For JPEG input (from ImageCapture): returns planes[0] directly.
 * - For YUV_420_888 (from ImageAnalysis): converts YUV → NV21 → YuvImage → JPEG.
 */
private fun yuv420ToJpeg(proxy: ImageProxy, quality: Int): ByteArray {
    val image = proxy.image ?: return ByteArray(0)
    val planes = image.planes
    val width = image.width
    val height = image.height

    // ImageCapture returns JPEG directly — no conversion needed
    if (image.format == ImageFormat.JPEG) {
        val buffer = planes[0].buffer
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        return bytes
    }

    // Convert YUV_420_888 → NV21 → JPEG
    val yPlane = planes[0]
    val uPlane = planes[1]
    val vPlane = planes[2]

    val nv21 = ByteArray(width * height * 3 / 2)

    // Copy Y plane (handle row stride)
    val yBuffer = yPlane.buffer
    yBuffer.position(0)
    if (yPlane.rowStride == width) {
        yBuffer.get(nv21, 0, width * height)
    } else {
        var pos = 0
        for (row in 0 until height) {
            yBuffer.position(row * yPlane.rowStride)
            yBuffer.get(nv21, pos, width)
            pos += width
        }
    }

    // Copy V and U planes interleaved (NV21 order: V then U)
    val uBuffer = uPlane.buffer
    val vBuffer = vPlane.buffer
    val uvWidth = width / 2
    val uvHeight = height / 2
    var uvPos = width * height

    for (row in 0 until uvHeight) {
        for (col in 0 until uvWidth) {
            val uIdx = row * uPlane.rowStride + col * uPlane.pixelStride
            val vIdx = row * vPlane.rowStride + col * vPlane.pixelStride
            vBuffer.position(vIdx)
            uBuffer.position(uIdx)
            nv21[uvPos++] = vBuffer.get()  // V first
            nv21[uvPos++] = uBuffer.get()  // U second
        }
    }

    val yuvImage = YuvImage(nv21, ImageFormat.NV21, width, height, null)
    val out = ByteArrayOutputStream()
    yuvImage.compressToJpeg(Rect(0, 0, width, height), quality, out)
    return out.toByteArray()
}
