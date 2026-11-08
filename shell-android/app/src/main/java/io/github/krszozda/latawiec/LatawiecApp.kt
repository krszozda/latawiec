package io.github.krszozda.latawiec

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

/**
 * Initializes Firebase from build properties instead of the
 * google-services plugin, so push is branded the same way as the rest of
 * the shell (-PfirebaseAppId=... on the gradle command line). A build
 * without the properties runs push-free.
 */
class LatawiecApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (BuildConfig.FIREBASE_APP_ID.isEmpty()) return
        FirebaseApp.initializeApp(
            this,
            FirebaseOptions.Builder()
                .setApplicationId(BuildConfig.FIREBASE_APP_ID)
                .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                .setApiKey(BuildConfig.FIREBASE_API_KEY)
                .build(),
        )
        // Both delivery paths share this channel: the manifest meta-data
        // points system-shown background messages at it, and the foreground
        // mirror in PushService posts to it.
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Notifications", NotificationManager.IMPORTANCE_DEFAULT),
        )
    }
}
