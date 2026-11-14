package io.github.krszozda.latawiec

import android.annotation.SuppressLint
import android.content.res.ColorStateList
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.drawable.ShapeDrawable
import android.graphics.drawable.shapes.OvalShape
import android.util.Log
import android.view.Menu
import android.view.MenuItem
import android.view.View
import androidx.core.graphics.drawable.toDrawable
import com.google.android.material.bottomnavigation.BottomNavigationView
import java.io.IOException
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Request
import okhttp3.Response

private const val TAG = "Latawiec"

/** Unselected tab color on a dark bar: white at 55%, as on iOS. */
private const val IDLE_ON_DARK = 0x8CFFFFFF.toInt()

/**
 * The bar across the bottom, as the manifest's tabs describe it. It knows
 * which screens the tabs root; the host decides what is on screen.
 */
// The shell has no XML layouts: the bar is built in code and handed its
// host, so the (Context, AttributeSet) constructors tooling looks for
// would have nothing to hand it.
@SuppressLint("ViewConstructor")
internal class TabBar(private val host: MainActivity) : BottomNavigationView(host) {

    /** Tab root screens in bar order; a deep link to one selects its tab. */
    var roots = emptyList<String>()
        private set

    // The platform's own look, for a theme that drops its colors.
    private val platformBackground = background
    private val platformIconTint = itemIconTintList
    private val platformTextColor = itemTextColor

    init {
        // A manifest with tabs reveals it; until then there is nothing to show.
        visibility = View.GONE
    }

    /**
     * Shows [tabs], keeping the selection when they root the same screens as
     * before — which is what a manifest refresh mid-session usually brings.
     * Answers whether the roots changed, since a new set leaves the host
     * showing a screen no tab roots any more.
     */
    fun show(tabs: List<Tab>, accent: String, bar: Int?): Boolean {
        val screens = tabs.map { it.screen }
        val rootsChanged = screens != roots
        val selected = if (rootsChanged) 0 else selectedItemId
        // menu.clear() resets the bar's selection, so restoring it below
        // fires a change event — which must not reach the old listener.
        setOnItemSelectedListener(null)
        menu.clear()
        tabs.forEachIndexed { index, tab ->
            val item = menu.add(Menu.NONE, index, index, tab.title)
            item.icon = placeholderIcon()
            tab.icon?.let { loadIcon(it, item) }
        }
        if (bar != null) setBackgroundColor(bar) else background = platformBackground
        tint(themeColor(accent, "accent"), bar)
        // Selection before the listener: restoring it must not re-navigate.
        selectedItemId = selected
        roots = screens
        listen()
        // Without this, Material routes a re-tap of the selected item to the
        // selected listener, which would reset the tab.
        setOnItemReselectedListener {}
        visibility = View.VISIBLE
        return rootsChanged
    }

    /** A one-screen app has no bar. */
    fun hide() {
        // Nothing the emptied bar does should navigate: the roots it would
        // navigate to are gone a line later.
        setOnItemSelectedListener(null)
        menu.clear()
        visibility = View.GONE
        roots = emptyList()
    }

    /**
     * Moves the highlight without navigating, for when the host already put
     * that tab's screen on display — restoring the stack after process death.
     */
    fun pointAt(index: Int) {
        setOnItemSelectedListener(null)
        selectedItemId = index
        listen()
    }

    private fun listen() {
        setOnItemSelectedListener { item ->
            host.showRoot(roots[item.itemId])
            true
        }
    }

    private fun tint(accent: Int?, bar: Int?) {
        if (accent == null && bar == null) {
            itemIconTintList = platformIconTint
            itemTextColor = platformTextColor
            return
        }
        val checked = intArrayOf(android.R.attr.state_checked)
        val selected = accent ?: platformIconTint?.getColorForState(checked, Color.GRAY) ?: Color.GRAY
        // Unselected items are a muted version of what reads on the bar.
        val idle = if (bar == null || isLight(bar)) Color.GRAY else IDLE_ON_DARK
        val colors = ColorStateList(arrayOf(checked, intArrayOf()), intArrayOf(selected, idle))
        itemIconTintList = colors
        itemTextColor = colors
    }

    // A menu item without an icon leaves a hole in the bar, so a tab with no
    // manifest icon gets a plain circle the item tint colors like the rest.
    private fun placeholderIcon() = ShapeDrawable(OvalShape()).apply {
        val size = (24 * resources.displayMetrics.density).toInt()
        intrinsicWidth = size
        intrinsicHeight = size
    }

    private fun loadIcon(path: String, item: MenuItem) {
        val request = Request.Builder().url(host.server.url + path).build()
        host.server.http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    Log.w(TAG, "icon $path failed: $e")
                }

                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        if (!it.isSuccessful) {
                            Log.w(TAG, "icon $path answered HTTP ${it.code}")
                            return
                        }
                        val bytes = it.body?.bytes() ?: return
                        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                        if (bitmap == null) {
                            Log.w(TAG, "icon $path did not decode as an image")
                            return
                        }
                        post {
                            if (!host.isDestroyed) item.icon = bitmap.toDrawable(resources)
                        }
                    }
                }
            },
        )
    }
}
