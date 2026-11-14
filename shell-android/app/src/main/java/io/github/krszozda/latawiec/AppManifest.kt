package io.github.krszozda.latawiec

import android.util.Log
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

private const val TAG = "Latawiec"

/** One entry of the tab bar: the screen it roots, and how it looks. */
internal data class Tab(val screen: String, val title: String, val icon: String?)

/** The shape of the app, as the server describes it at /manifest. */
internal data class AppManifest(
    /** Where a rejected token sends the user; null means no login at all. */
    val login: String?,
    val push: Boolean,
    /** Dev keeps the live-reload socket; production fetches and caches. */
    val dev: Boolean,
    /** Cached screens belong to a version; a new one drops them. */
    val version: String?,
    /** Empty for a one-screen app, which shows no bar. */
    val tabs: List<Tab>,
    /** Hex color for the bar's selected item, empty for the default. */
    val accent: String,
    /** Hex color behind every screen, empty for the platform's own. */
    val background: String,
    /** Hex color of the tab bar, empty for the platform's own. */
    val bar: String,
    /** Serialized back, for the screen cache to boot the next cold start from. */
    val raw: String,
)

internal fun parseManifest(json: JSONObject): AppManifest = AppManifest(
    login = json.opt("login") as? String,
    push = json.optBoolean("push"),
    dev = json.optBoolean("dev", true),
    version = json.opt("version") as? String,
    tabs = parseTabs(json.optJSONArray("tabs")),
    accent = json.optJSONObject("theme")?.optString("accent").orEmpty(),
    background = json.optJSONObject("theme")?.optString("background").orEmpty(),
    bar = json.optJSONObject("theme")?.optString("bar").orEmpty(),
    raw = json.toString(),
)

/** A malformed array is worth no more than a missing one: the shell shows no bar. */
private fun parseTabs(tabs: JSONArray?): List<Tab> {
    if (tabs == null) return emptyList()
    return try {
        (0 until tabs.length()).map { i ->
            val tab = tabs.getJSONObject(i)
            Tab(
                screen = tab.getString("screen"),
                title = tab.getString("title"),
                icon = if (tab.isNull("icon")) null else tab.getString("icon"),
            )
        }
    } catch (e: JSONException) {
        Log.w(TAG, "manifest tabs are malformed: $e")
        emptyList()
    }
}
