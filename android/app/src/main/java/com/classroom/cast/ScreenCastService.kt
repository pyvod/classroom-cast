package com.classroom.cast

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.view.Display
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import java.io.ByteArrayOutputStream

class ScreenCastService : Service() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var imageReader: ImageReader? = null
    private var isRunning = false

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification()
        startForeground(1, notification)

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, -1) ?: -1
        val data = intent?.getParcelableExtra(EXTRA_INTENT_DATA, android.content.Intent::class.java)
        if (resultCode == -1 || data == null) {
            stopSelf()
            return START_NOT_STICKY
        }

        startCapture(resultCode, data)
        return START_STICKY
    }

    private fun startCapture(resultCode: Int, data: Intent) {
        val mediaProjectionManager = getSystemService(MEDIA_PROJECTION_SERVICE) as
                android.media.projection.MediaProjectionManager
        val projection = mediaProjectionManager.getMediaProjection(resultCode, data)

        // Capture at 720p for performance
        val width = 1280
        val height = 720
        val density = resources.displayMetrics.densityDpi

        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)

        val virtualDisplay = projection?.createVirtualDisplay(
            "ScreenCast",
            width, height, density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader?.surface, null, null
        )

        isRunning = true

        scope.launch {
            var lastCapture = 0L
            val frameInterval = 100L // ~10fps

            while (isRunning) {
                val now = System.currentTimeMillis()
                if (now - lastCapture < frameInterval) {
                    delay(10)
                    continue
                }

                val image = imageReader?.acquireLatestImage()
                if (image != null) {
                    val bitmap = imageToBitmap(image)
                    image.close()

                    if (bitmap != null) {
                        val stream = ByteArrayOutputStream()
                        bitmap.compress(Bitmap.CompressFormat.JPEG, 50, stream)
                        val jpegData = stream.toByteArray()
                        bitmap.recycle()

                        castClient?.sendFrame(jpegData)
                        lastCapture = now
                    }
                } else {
                    delay(10)
                }
            }

            // Cleanup
            virtualDisplay?.release()
            projection?.stop()
            imageReader?.close()
            imageReader = null
        }
    }

    private fun imageToBitmap(image: android.media.Image): Bitmap? {
        val planes = image.planes
        val buffer = planes[0].buffer
        val pixelStride = planes[0].pixelStride
        val rowStride = planes[0].rowStride
        val rowPadding = rowStride - pixelStride * image.width

        val bitmap = Bitmap.createBitmap(
            image.width + rowPadding / pixelStride,
            image.height,
            Bitmap.Config.ARGB_8888
        )
        bitmap.copyPixelsFromBuffer(buffer)
        return if (rowPadding == 0) bitmap
        else Bitmap.createBitmap(bitmap, 0, 0, image.width, image.height)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        isRunning = false
        scope.cancel()
        castClient?.sendCastStop()
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.channel_name),
                NotificationManager.IMPORTANCE_LOW
            )
            channel.description = getString(R.string.channel_desc)
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("班级投屏")
            .setContentText("正在投屏中...")
            .setSmallIcon(android.R.drawable.ic_menu_share)
            .setOngoing(true)
            .build()
    }

    companion object {
        const val CHANNEL_ID = "screen_cast"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_INTENT_DATA = "intent_data"

        private var castClient: CastClient? = null

        fun setCastClient(client: CastClient?) {
            castClient = client
        }

        fun start(context: Context, resultCode: Int, data: Intent, client: CastClient) {
            setCastClient(client)
            val intent = Intent(context, ScreenCastService::class.java).apply {
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_INTENT_DATA, data)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, ScreenCastService::class.java))
            setCastClient(null)
        }
    }
}
