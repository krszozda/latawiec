package io.github.krszozda.latawiec

import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.util.Locale

private const val TAG = "Latawiec"

/** How long a RequestLocation waits for a fix before giving up on one. */
private const val FIX_TIMEOUT_MS = 10_000L

/**
 * One fix, from whichever provider answers first. The caller is told
 * exactly once, so a screen variable is never written twice and a
 * RequestLocation that no longer has anywhere to land can drop the ask.
 */
class LocationFinder(private val context: Context) {

    private val handler = Handler(Looper.getMainLooper())
    private val listeners = mutableListOf<LocationListener>()
    private var timeout: Runnable? = null
    private var waiting: ((String) -> Unit)? = null

    /**
     * Every enabled provider is asked at once and the first fix wins: GPS
     * gives the best one but indoors it never arrives, where the network
     * provider answers in a second. `deliver` runs once, on the main
     * thread, with "" when there is no fix to be had.
     */
    fun find(deliver: (String) -> Unit) {
        cancel()
        waiting = deliver
        val manager = context.getSystemService(LocationManager::class.java)
        val providers = manager?.getProviders(true).orEmpty()
        if (manager == null || providers.isEmpty()) {
            answer("")
            return
        }
        for (provider in providers) {
            val listener = FixListener()
            listeners += listener
            try {
                manager.requestLocationUpdates(provider, 0L, 0f, listener, handler.looper)
            } catch (e: SecurityException) {
                Log.w(TAG, "location updates from $provider refused: $e")
            }
        }
        val giveUp = Runnable { answer("") }
        timeout = giveUp
        handler.postDelayed(giveUp, FIX_TIMEOUT_MS)
    }

    /** Leaving the app drops the ask: no listeners, no late empty answer. */
    fun cancel() {
        waiting = null
        timeout?.let(handler::removeCallbacks)
        timeout = null
        val manager = context.getSystemService(LocationManager::class.java)
        for (listener in listeners) manager?.removeUpdates(listener)
        listeners.clear()
    }

    /** First answer (or the timeout) wins; the rest find nothing waiting. */
    private fun answer(value: String) {
        val deliver = waiting ?: return
        cancel()
        deliver(value)
    }

    private inner class FixListener : LocationListener {
        override fun onLocationChanged(location: Location) {
            // Locale.US: a comma as the decimal separator would cut the pair
            // into three numbers on a Polish phone.
            answer(String.format(Locale.US, "%.6f,%.6f", location.latitude, location.longitude))
        }

        // Default methods on modern SDKs, abstract back on API 26-29, where
        // leaving them out crashes the moment the system calls one.
        @Deprecated("Deprecated in Java")
        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit

        override fun onProviderEnabled(provider: String) = Unit

        override fun onProviderDisabled(provider: String) = Unit
    }
}
