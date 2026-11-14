package io.github.krszozda.latawiec

import android.annotation.SuppressLint
import android.net.Uri
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.FrameLayout
import android.widget.ProgressBar
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.yandex.div.DivDataTag
import com.yandex.div.core.player.DivPlayerView
import com.yandex.div.core.view2.Div2View
import com.yandex.div.data.DivParsingEnvironment
import com.yandex.div.json.ParsingErrorLogger
import com.yandex.div2.DivData
import java.io.IOException
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

private const val TAG = "Latawiec"
private const val RECONNECT_DELAY_MS = 1_000L
private const val RECONNECT_DELAY_MAX_MS = 30_000L

/** The server's WebSocket close code for a missing or rejected token. */
private const val NOT_AUTHORIZED = 4401

/**
 * One screen of the stack: its own DivView, spinner, and transport. In dev
 * every stacked screen keeps its socket, so the whole stack live-reloads;
 * in production the screen renders from the cache and revalidates.
 */
// The shell has no XML layouts: a screen is built in code and handed its
// host, so the (Context, AttributeSet) constructors tooling looks for
// would have nothing to hand it.
@SuppressLint("ViewConstructor")
class ScreenView(
    private val host: MainActivity,
    val name: String,
) : FrameLayout(host) {

    private val divView = Div2View(host.divContext)
    private val spinner = ProgressBar(context)

    // Routed values ride in the name; encoding each segment keeps them
    // from reshaping the request path (iOS encodes the same way).
    private val encodedName = name.split("/").joinToString("/", transform = Uri::encode)
    private var socket: WebSocket? = null
    private var reconnectDelayMs = RECONNECT_DELAY_MS

    /** Poll interval of a refresh=N screen, from its response header. */
    private var pollSeconds: Long? = null

    private val swipe = SwipeRefreshLayout(context).apply {
        isEnabled = false
        addView(divView)
        // The gesture must not steal scrolls from a list that can still
        // go up — DivKit's lists live somewhere inside the view tree.
        setOnChildScrollUpCallback { _, _ -> canAnyScrollUp(divView) }
        setOnRefreshListener { if (host.devMode) connect() else fetch() }
    }

    init {
        paint(host.screenBackground)
        addView(swipe, LayoutParams(MATCH_PARENT, MATCH_PARENT))
        addView(spinner, LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.CENTER))
    }

    /** Theme.background, or the platform's own for null. */
    fun paint(color: Int?) {
        // Screens stack on top of each other; without an opaque
        // background the covered screen bleeds through.
        if (color != null) {
            setBackgroundColor(color)
            return
        }
        val platform = TypedValue()
        context.theme.resolveAttribute(android.R.attr.colorBackground, platform, true)
        setBackgroundColor(platform.data)
    }

    private fun canAnyScrollUp(view: View): Boolean {
        if (view.canScrollVertically(-1)) return true
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                if (canAnyScrollUp(view.getChildAt(i))) return true
            }
        }
        return false
    }

    fun start() {
        if (host.devMode) connect() else fetch()
    }

    fun stop() {
        socket?.cancel()
    }

    /** Releases DivKit resources (players included); after removal. */
    fun cleanup() {
        divView.cleanup()
    }

    /** An upload finished: hand its value to this screen's card. */
    fun setVariable(name: String, value: String) {
        divView.setVariable(name, value)?.let {
            Log.w(TAG, "setting $name failed: $it")
        }
    }

    /** Covered by a push: videos stop decoding but keep their intent. */
    fun holdVideos() {
        forEachPlayer(this) { it.hold() }
    }

    /** Back on top: autoplaying videos pick up again. */
    fun resumeVideos() {
        forEachPlayer(this) { it.resume() }
    }

    private fun forEachPlayer(group: ViewGroup, action: (HoldablePlayer) -> Unit) {
        for (i in 0 until group.childCount) {
            when (val child = group.getChildAt(i)) {
                is DivPlayerView ->
                    (child.getAttachedPlayer() as? HoldablePlayer)?.let(action)
                is ViewGroup -> forEachPlayer(child, action)
            }
        }
    }

    /**
     * The screen arrives over this socket on connect. The server holds it
     * open; when it restarts (`uvicorn --reload` on every code change) the
     * socket drops and the reconnect delivers the fresh screen — that is
     * the live-reload loop.
     *
     * Callbacks of a superseded socket can still fire (cancel() itself
     * triggers onFailure), so each one acts only when its webSocket is
     * still the one in the `socket` field.
     */
    private fun connect() {
        socket?.cancel()
        val url = "${host.server.url.replaceFirst("http", "ws")}/ws/screens/$encodedName"
        socket = host.server.sockets.newWebSocket(
            host.server.authorized(Request.Builder().url(url)).build(),
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    if (webSocket == socket) render(text)
                }

                // OkHttp does not finish the close handshake by itself:
                // without this close() call onClosed never fires and the
                // reload loop stalls.
                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(1000, null)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    if (webSocket != socket) return
                    if (code == NOT_AUTHORIZED) {
                        post { if (!host.isDestroyed) host.onUnauthorized() }
                    } else {
                        later { connect() }
                    }
                }

                override fun onFailure(
                    webSocket: WebSocket,
                    t: Throwable,
                    response: Response?,
                ) {
                    Log.w(TAG, "socket to $url failed: $t")
                    if (webSocket == socket) later { connect() }
                }
            },
        )
    }

    /**
     * Production path: render the last-known screen from disk right away,
     * then revalidate over GET and swap in the fresh payload — unless the
     * cached copy is "static", which lives until the manifest version
     * moves.
     */
    private fun fetch() {
        // A response that outlives a sign-out wipe must not store.
        val asOf = host.screenCache.generation
        // Mid-pull the content is already on screen: rendering the
        // cached copy would snap the indicator shut within a frame.
        val cached = if (swipe.isRefreshing) null else host.screenCache.load(name)
        if (cached != null) {
            render(cached.payload)
            when {
                cached.policy == "static" -> return
                // A cached live screen subscribes straight away — the
                // socket's backoff covers an unreachable server, and its
                // first message is the fresh render.
                cached.policy == "live" -> {
                    post { if (!host.isDestroyed && isAttachedToWindow) connect() }
                    return
                }
                // The interval from the cache keeps a polled screen's
                // rhythm even when the revalidation fetch fails.
                cached.policy.startsWith("poll:") ->
                    pollSeconds = cached.policy.substringAfter(':').toLongOrNull()
            }
        }
        val url = "${host.server.url}/screens/$encodedName"
        val request = host.server.authorized(Request.Builder().url(url)).build()
        host.server.http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    // With a cached copy on screen this is offline mode; a
                    // blank screen keeps retrying on the socket's backoff,
                    // and a polled screen keeps its rhythm.
                    Log.w(TAG, "screen $name fetch failed: $e")
                    post { swipe.isRefreshing = false }
                    if (cached == null) later { fetch() } else schedulePoll()
                }

                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        if (it.code == 401) {
                            post { if (!host.isDestroyed) host.onUnauthorized() }
                            return
                        }
                        if (!it.isSuccessful) {
                            Log.w(TAG, "screen $name answered HTTP ${it.code}")
                            post { swipe.isRefreshing = false }
                            if (cached == null) later { fetch() } else schedulePoll()
                            return
                        }
                        val payload = it.body?.string() ?: return
                        val header = it.header("Cache-Control").orEmpty()
                        val live = it.header("X-Latawiec-Live") != null
                        val refreshSeconds =
                            it.header("X-Latawiec-Refresh")?.toLongOrNull()
                        val policy = when {
                            "no-store" in header -> "no-store"
                            "immutable" in header -> "static"
                            live -> "live"
                            refreshSeconds != null -> "poll:$refreshSeconds"
                            else -> "swr"
                        }
                        if (policy != "no-store") {
                            host.screenCache.store(name, policy, payload, asOf)
                        }
                        if (it.header("X-Latawiec-Refreshable") != null) {
                            post { swipe.isEnabled = true }
                        }
                        render(payload)
                        it.header("X-Latawiec-Manifest")?.let { seen ->
                            // Handed over on main: the applied fingerprint
                            // this is compared against lives there.
                            post { if (!host.isDestroyed) host.onManifestSeen(seen) }
                        }
                        if (live) {
                            // A live screen subscribes after its first
                            // render; every app.refresh() lands here.
                            post { if (!host.isDestroyed && isAttachedToWindow) connect() }
                        } else {
                            pollSeconds = refreshSeconds
                            schedulePoll()
                        }
                    }
                }
            },
        )
    }

    /**
     * Polled screens refetch on their interval, but only while truly on
     * display: a covered or backgrounded screen stops ticking and
     * resumePolling() picks it back up.
     */
    private fun schedulePoll() {
        val seconds = pollSeconds ?: return
        postDelayed(
            {
                if (!host.isDestroyed && isAttachedToWindow && host.isPolling(this)) fetch()
            },
            seconds * 1000,
        )
    }

    /** Back on top (pop, or app foregrounded): refetch and tick again. */
    fun resumePolling() {
        if (pollSeconds != null && isAttachedToWindow) fetch()
    }

    /** Backs off while the server stays away; a delivered screen resets it. */
    private fun later(retry: () -> Unit) {
        postDelayed(
            { if (!host.isDestroyed && isAttachedToWindow) retry() },
            reconnectDelayMs,
        )
        reconnectDelayMs = (reconnectDelayMs * 2).coerceAtMost(RECONNECT_DELAY_MAX_MS)
    }

    private fun render(payload: String) {
        reconnectDelayMs = RECONNECT_DELAY_MS
        val data = parseCard(JSONObject(payload))
        post {
            if (!host.isDestroyed) {
                divView.setData(data, DivDataTag(name))
                spinner.visibility = View.GONE
                swipe.isRefreshing = false
            }
        }
    }
}

private fun parseCard(payload: JSONObject): DivData {
    val environment = DivParsingEnvironment(ParsingErrorLogger.LOG)
    payload.optJSONObject("templates")?.let(environment::parseTemplates)
    return DivData(environment, payload.getJSONObject("card"))
}
