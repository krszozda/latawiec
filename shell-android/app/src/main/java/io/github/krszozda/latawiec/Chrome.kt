package io.github.krszozda.latawiec

import android.app.Activity
import android.os.Build
import android.util.Log
import androidx.core.graphics.ColorUtils
import androidx.core.graphics.toColorInt
import androidx.core.view.WindowCompat

private const val TAG = "Latawiec"

/** A manifest color, or null for the platform's own when unset or unreadable. */
internal fun themeColor(hex: String, field: String): Int? {
    if (hex.isEmpty()) return null
    return try {
        hex.toColorInt()
    } catch (e: IllegalArgumentException) {
        Log.w(TAG, "theme $field $hex is not a color: $e")
        null
    }
}

/** Whether dark icons and text read on [color]; iOS draws the same line. */
internal fun isLight(color: Int): Boolean = ColorUtils.calculateLuminance(color) > 0.5

/**
 * The status and navigation bars, matched to what the theme puts behind
 * them. Whatever the platform theme gave them is remembered at start, so a
 * manifest without colors — or one that drops them mid-session — leaves
 * the bars exactly as an unthemed app has them.
 */
internal class SystemBars(activity: Activity) {
    private val window = activity.window
    private val controller = WindowCompat.getInsetsController(window, window.decorView)
    private val platformLightTop = controller.isAppearanceLightStatusBars
    private val platformLightBottom = controller.isAppearanceLightNavigationBars

    // Below API 35 the shell is not edge-to-edge and the bars have fills of
    // their own; those setters are deprecated only because 35+ ignores them.
    @Suppress("DEPRECATION")
    private val platformTop = window.statusBarColor

    @Suppress("DEPRECATION")
    private val platformBottom = window.navigationBarColor

    fun paint(top: Int?, bottom: Int?) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            @Suppress("DEPRECATION")
            window.statusBarColor = top ?: platformTop
            @Suppress("DEPRECATION")
            window.navigationBarColor = bottom ?: platformBottom
        }
        controller.isAppearanceLightStatusBars = top?.let(::isLight) ?: platformLightTop
        controller.isAppearanceLightNavigationBars = bottom?.let(::isLight) ?: platformLightBottom
    }
}
