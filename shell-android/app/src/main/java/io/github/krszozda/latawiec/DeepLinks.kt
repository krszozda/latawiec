package io.github.krszozda.latawiec

import android.content.Intent
import android.net.Uri

/** A deep link carries the screen in its URI, a push tap in an extra. */
fun linkedScreen(intent: Intent): String? =
    intent.data?.let(::screenPath) ?: intent.getStringExtra("screen")?.let(::rawScreenPath)

/**
 * Maps a deep-link URI to a screen path. App Links carry the screen in
 * the https path; a custom scheme starts it at the host, so
 * "latawiec://product/42" opens the screen "product/42". The link is
 * untrusted: one whose decoded segments could reshape the request path
 * they end up in is dropped.
 */
private fun screenPath(uri: Uri): String? {
    val path = uri.path.orEmpty().trim('/')
    val screen = when (uri.scheme?.lowercase()) {
        "http", "https" -> path
        else -> listOf(uri.host.orEmpty(), path).filter(String::isNotEmpty).joinToString("/")
    }
    return rawScreenPath(screen)
}

/** The same segment rules for a bare path (a push payload's "screen"). */
private fun rawScreenPath(raw: String): String? {
    val screen = raw.trim('/')
    if (screen.isEmpty()) return null
    val segments = screen.split("/")
    if (segments.any { it.isEmpty() || it == "." || it == ".." }) return null
    return screen
}
