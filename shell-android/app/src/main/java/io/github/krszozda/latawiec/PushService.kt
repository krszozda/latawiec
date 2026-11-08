package io.github.krszozda.latawiec

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.LocaleList
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.io.IOException
import java.util.TimeZone
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject

private const val TAG = "Latawiec"

/** One channel for both delivery paths; see the manifest meta-data. */
internal const val CHANNEL = "latawiec"

/** Hands the platform's push token to the server's @app.device hook. */
object DeviceRegistry {
    private val http = OkHttpClient()

    fun register(context: Context, token: String) {
        // Always the baked-in URL: the debug-only serverUrl extra lives on
        // the activity, and no Firebase-less test exercises this path.
        val body = JSONObject().put("token", token).toString()
        val builder = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/devices")
            .post(body.toRequestBody("application/json".toMediaType()))
        TokenStore(context).load()?.let { builder.header("Authorization", "Bearer $it") }
        builder.header("Accept-Language", LocaleList.getDefault().toLanguageTags())
        builder.header("X-Latawiec-Platform", "android")
        builder.header("X-Latawiec-Timezone", TimeZone.getDefault().id)
        builder.header("X-Latawiec-App-Version", BuildConfig.VERSION_NAME)
        http.newCall(builder.build()).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    Log.w(TAG, "device registration failed: $e")
                }

                override fun onResponse(call: Call, response: Response) {
                    response.close()
                }
            },
        )
    }
}

class PushService : FirebaseMessagingService() {

    /** Fires for the first token after install and for every rotation. */
    override fun onNewToken(token: String) {
        DeviceRegistry.register(this, token)
    }

    /**
     * Only foreground deliveries land here — the system itself shows
     * background notification messages. Mirroring them keeps both states
     * alike, and the tap carries the payload's screen into MainActivity
     * exactly as a system-shown notification would.
     */
    override fun onMessageReceived(message: RemoteMessage) {
        val notification = message.notification ?: return
        val manager = getSystemService(NotificationManager::class.java)
        // Tapped "outside of the context of an existing activity" per the
        // PendingIntent.getActivity contract.
        val tap = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        message.data["screen"]?.let { tap.putExtra("screen", it) }
        val stamp = (SystemClock.elapsedRealtime() and 0x7FFFFFFF).toInt()
        val pending = PendingIntent.getActivity(
            this,
            stamp,
            tap,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val built = NotificationCompat.Builder(this, CHANNEL)
            // The template ships no branding; swap in your icon with the
            // launcher one (docs/shipping.md).
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(notification.title)
            .setContentText(notification.body)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()
        manager.notify(stamp, built)
    }
}
