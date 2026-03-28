package com.example.ut_nguyen_mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return
        }

        val manager =
            getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val updatesChannel = NotificationChannel(
            "icare_updates",
            "Icare cap nhat",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply {
            description = "Thong bao chung cua Icare"
        }

        val chatChannel = NotificationChannel(
            "family_chat",
            "Tin nhan gia dinh",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Thong bao tin nhan tu nguoi than"
        }

        val incomingCallChannel = NotificationChannel(
            "incoming_calls",
            "Cuoc goi den",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Thong bao cuoc goi khan cap"
            enableVibration(true)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            val ringtoneUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            val audioAttributes = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
            setSound(ringtoneUri, audioAttributes)
        }

        manager.createNotificationChannels(
            listOf(updatesChannel, chatChannel, incomingCallChannel)
        )
    }
}
