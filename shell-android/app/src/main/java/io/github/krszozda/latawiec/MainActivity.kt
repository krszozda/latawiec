package io.github.krszozda.latawiec

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.ShapeDrawable
import android.graphics.drawable.shapes.OvalShape
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.LocaleList
import android.provider.OpenableColumns
import android.text.InputType
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.snackbar.Snackbar
import com.google.firebase.messaging.FirebaseMessaging
import com.yandex.div.DivDataTag
import com.yandex.div.coil.CoilDivImageLoader
import com.yandex.div.core.Div2Context
import com.yandex.div.core.DivActionHandler
import com.yandex.div.core.DivConfiguration
import com.yandex.div.core.DivViewFacade
import com.yandex.div.core.view2.Div2View
import com.yandex.div.data.DivParsingEnvironment
import com.yandex.div.json.ParsingErrorLogger
import com.yandex.div.json.expressions.ExpressionResolver
import com.yandex.div2.DivAction
import com.yandex.div2.DivData
import com.yandex.div2.DivSightAction
import java.io.File
import java.io.IOException
import java.util.Locale
import java.util.TimeZone
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.BufferedSink
import okio.source
import org.json.JSONException
import org.json.JSONObject

private const val TAG = "Latawiec"
private const val RECONNECT_DELAY_MS = 1_000L
private const val RECONNECT_DELAY_MAX_MS = 30_000L
private const val PUSH_ANIMATION_MS = 250L

/** How long a RequestLocation waits for a fix before giving up on one. */
private const val FIX_TIMEOUT_MS = 10_000L

/** How long a camera shot stays in the cache before it is swept. */
private const val PHOTO_KEEP_MS = 24 * 60 * 60 * 1000L

/** The server's WebSocket close code for a missing or rejected token. */
private const val NOT_AUTHORIZED = 4401

/** What OpenUrl may leave the app for; anything else is refused. */
private val OPENABLE_SCHEMES = setOf("http", "https", "mailto", "tel", "sms")

class MainActivity : AppCompatActivity() {

    private val http = OkHttpClient()

    // Instrumentation tests point the shell at a per-test server. Debug-only:
    // the activity is exported, so in a release build any app could repoint
    // the shell at its own server with this extra. A build with no baked-in
    // URL (the generic try-it-out APK) falls back to the address the user
    // typed on first start.
    private val serverUrl by lazy {
        intent.getStringExtra("serverUrl").takeIf { BuildConfig.DEBUG }
            ?: BuildConfig.SERVER_URL.ifEmpty {
                getSharedPreferences("latawiec-config", MODE_PRIVATE)
                    .getString("serverUrl", "").orEmpty()
            }
    }
    private lateinit var div2Context: Div2Context
    private lateinit var stackHost: FrameLayout
    private lateinit var bottomBar: BottomNavigationView
    private lateinit var tokenStore: TokenStore
    private lateinit var screenCache: ScreenCache
    private var token: String? = null

    /** Dev keeps the live-reload socket; production fetches and caches. */
    private var devMode = true

    /** Screen from the manifest to show when the server answers 401/4401. */
    private var loginScreen: String? = null

    /** Tab root screens in bar order; a deep link to one selects its tab. */
    private var tabRoots = emptyList<String>()

    /** A deep link that arrived before the manifest; opened once it applies. */
    private var pendingDeepLink: String? = null
    private var manifestApplied = false

    /** Fingerprint of the applied manifest; a mismatch means refetch. */
    private var manifestHash: String? = null
    private var askedForNotifications = false
    private var pushEnabled = false

    /** Which screen variable (and whose screen) the in-flight pick feeds. */
    private var pendingPickVariable: String? = null
    private var pendingPickScreen: ScreenView? = null

    /** Where the camera app was told to write, and where we read it back. */
    private var pendingPhotoUri: Uri? = null
    private val pickMedia =
        registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
            val variable = pendingPickVariable
            val screen = pendingPickScreen
            pendingPickVariable = null
            pendingPickScreen = null
            if (uri != null && variable != null) uploadPicked(uri, variable, screen)
        }

    private val takePhoto =
        registerForActivityResult(ActivityResultContracts.TakePicture()) { taken ->
            val variable = pendingPickVariable
            val screen = pendingPickScreen
            val uri = pendingPhotoUri
            pendingPickVariable = null
            pendingPickScreen = null
            pendingPhotoUri = null
            if (taken && variable != null && uri != null) uploadPicked(uri, variable, screen)
        }

    /** A RequestLocation waiting on the permission prompt or on a fix. */
    private data class LocationAsk(
        val variable: String,
        val action: String?,
        val screen: ScreenView?,
    )

    private var pendingLocation: LocationAsk? = null
    private val fixListeners = mutableListOf<LocationListener>()
    private var fixTimeout: Runnable? = null
    private val askLocation =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
            // Coarse alone is a yes: a city-level fix still answers "where am I".
            if (grants.values.any { it }) requestFix() else deliverLocation("")
        }

    /**
     * One view per screen, stacked like iOS's navigation controllers: popping
     * uncovers the previous view with its DivKit variables intact, instead of
     * refetching the screen and losing what the user typed.
     */
    private val screens = ArrayDeque<ScreenView>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        tokenStore = TokenStore(this)
        token = tokenStore.load()
        screenCache = ScreenCache(this)
        val configuration = DivConfiguration.Builder(CoilDivImageLoader(this))
            .actionHandler(LatawiecActionHandler())
            .divPlayerFactory(SystemPlayerFactory())
            .build()
        div2Context = Div2Context(this, configuration)
        bottomBar = BottomNavigationView(this).apply { visibility = View.GONE }
        stackHost = FrameLayout(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(stackHost, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f))
            addView(bottomBar, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        }
        setContentView(root, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (screens.size > 1) pop() else finish()
                }
            },
        )

        // On recreation the task's root intent replays; the link opened once
        // (and survives the recreate() a first-start setup triggers).
        pendingDeepLink = if (savedInstanceState == null) {
            linkedScreen(intent)
        } else {
            savedInstanceState.getString("pendingDeepLink")
        }
        if (savedInstanceState != null) {
            pendingPickVariable = savedInstanceState.getString("pendingPickVariable")
            pendingPhotoUri = savedInstanceState.getString("pendingPhotoUri")?.let(Uri::parse)
            // The screen is gone with the old activity; the fix lands on
            // whichever screen is showing when it arrives.
            savedInstanceState.getString("pendingLocationVariable")?.let {
                pendingLocation = LocationAsk(
                    it,
                    savedInstanceState.getString("pendingLocationAction"),
                    null,
                )
            }
        }
        if (serverUrl.isEmpty()) {
            askForServer()
            return
        }
        fetchManifest()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString("pendingDeepLink", pendingDeepLink)
        // A pick's ActivityResult survives process death; its variable must
        // too, or the redelivered photo has nowhere to land. The screen
        // stack does not survive, so the value reaches the rebuilt screen
        // only if that screen declares the same variable. The permission
        // prompt behind a RequestLocation is the same story.
        outState.putString("pendingPickVariable", pendingPickVariable)
        outState.putString("pendingPhotoUri", pendingPhotoUri?.toString())
        outState.putString("pendingLocationVariable", pendingLocation?.variable)
        outState.putString("pendingLocationAction", pendingLocation?.action)
    }

    /** The generic APK ships without a server; the first start asks for one. */
    private fun askForServer() {
        val input = EditText(this).apply {
            hint = "https://your-server.example.com"
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            // A typo'd address comes back for editing, not retyping.
            setText(
                getSharedPreferences("latawiec-config", MODE_PRIVATE)
                    .getString("serverUrl", ""),
            )
        }
        val frame = FrameLayout(this).apply {
            val pad = (20 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
            addView(input, FrameLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        }
        AlertDialog.Builder(this)
            .setTitle("Where does this app live?")
            .setMessage("Enter your Latawiec server's URL.")
            .setView(frame)
            .setCancelable(false)
            .setPositiveButton("Connect") { _, _ ->
                val url = input.text.toString().trim().trimEnd('/')
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    getSharedPreferences("latawiec-config", MODE_PRIVATE)
                        .edit().putString("serverUrl", url).apply()
                }
                // Rebuilds the activity so the lazy serverUrl re-resolves;
                // a rejected value simply asks again.
                recreate()
            }
            .show()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val screen = linkedScreen(intent) ?: return
        if (manifestApplied) openDeepLink(screen) else pendingDeepLink = screen
    }

    /** A deep link carries the screen in its URI, a push tap in an extra. */
    private fun linkedScreen(intent: Intent): String? =
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

    /** A tab root selects its tab; any other screen pushes onto the stack. */
    private fun openDeepLink(screen: String) {
        val tab = tabRoots.indexOf(screen)
        when {
            tab < 0 -> showScreen(screen)
            // Selecting the already-selected item only fires the (empty)
            // reselected listener; the link still means "back to this root".
            bottomBar.selectedItemId == tab -> showRoot(screen)
            else -> bottomBar.selectedItemId = tab
        }
    }

    /** Gates the poll ticks: a backgrounded app must not keep fetching. */
    private var resumed = false

    override fun onResume() {
        super.onResume()
        resumed = true
        screens.lastOrNull()?.resumePolling()
        screens.lastOrNull()?.resumeVideos()
        // The chrome may have changed while the app was away; the first
        // resume is still mid-boot (manifestApplied false) and skips this.
        if (manifestApplied) fetchManifest()
    }

    override fun onPause() {
        resumed = false
        super.onPause()
    }

    override fun onDestroy() {
        cancelFix()
        screens.forEach(ScreenView::stop)
        super.onDestroy()
    }

    /** Tab roots replace the whole history: system back on one exits the app. */
    private fun showRoot(name: String) {
        screens.forEach {
            it.stop()
            stackHost.removeView(it)
            it.cleanup()
        }
        screens.clear()
        push(name, animated = false)
    }

    private fun showScreen(name: String) {
        // A double-tap would stack the same screen twice and break back.
        if (name != screens.lastOrNull()?.name) push(name, animated = true)
    }

    private fun push(name: String, animated: Boolean) {
        // The covered screen must not keep playing behind the new one.
        screens.lastOrNull()?.holdVideos()
        val screen = ScreenView(name)
        screens.addLast(screen)
        stackHost.addView(screen, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        if (animated) {
            screen.translationX = stackHost.width.toFloat()
            screen.animate().translationX(0f).setDuration(PUSH_ANIMATION_MS)
        }
        screen.start()
    }

    private fun pop() {
        val leaving = screens.removeLast()
        // Stopped before the slide: a teardown mid-animation would skip the
        // end action and leak the socket.
        leaving.stop()
        screens.lastOrNull()?.resumePolling()
        screens.lastOrNull()?.resumeVideos()
        leaving.animate()
            .translationX(stackHost.width.toFloat())
            .setDuration(PUSH_ANIMATION_MS)
            .withEndAction {
                stackHost.removeView(leaving)
                leaving.cleanup()
            }
    }

    /**
     * One screen of the stack: its own DivView, spinner, and transport. In dev
     * every stacked screen keeps its socket, so the whole stack live-reloads;
     * in production the screen renders from the cache and revalidates.
     */
    private inner class ScreenView(val name: String) : FrameLayout(this@MainActivity) {

        private val divView = Div2View(div2Context)
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
            setOnRefreshListener { if (devMode) connect() else fetch() }
        }

        init {
            // Screens stack on top of each other; without an opaque
            // background the covered screen bleeds through.
            val background = TypedValue()
            context.theme.resolveAttribute(android.R.attr.colorBackground, background, true)
            setBackgroundColor(background.data)
            addView(swipe, LayoutParams(MATCH_PARENT, MATCH_PARENT))
            addView(spinner, LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.CENTER))
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
            if (devMode) connect() else fetch()
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

        private fun forEachPlayer(group: ViewGroup, action: (SystemPlayer) -> Unit) {
            for (i in 0 until group.childCount) {
                when (val child = group.getChildAt(i)) {
                    is SystemPlayerView ->
                        (child.getAttachedPlayer() as? SystemPlayer)?.let(action)
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
            val url = "${serverUrl.replaceFirst("http", "ws")}/ws/screens/$encodedName"
            socket = http.newWebSocket(
                authorized(Request.Builder().url(url)).build(),
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
                            post { if (!isDestroyed) onUnauthorized() }
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
            val asOf = screenCache.generation
            // Mid-pull the content is already on screen: rendering the
            // cached copy would snap the indicator shut within a frame.
            val cached = if (swipe.isRefreshing) null else screenCache.load(name)
            if (cached != null) {
                render(cached.payload)
                when {
                    cached.policy == "static" -> return
                    // A cached live screen subscribes straight away — the
                    // socket's backoff covers an unreachable server, and its
                    // first message is the fresh render.
                    cached.policy == "live" -> {
                        post { if (!isDestroyed && isAttachedToWindow) connect() }
                        return
                    }
                    // The interval from the cache keeps a polled screen's
                    // rhythm even when the revalidation fetch fails.
                    cached.policy.startsWith("poll:") ->
                        pollSeconds = cached.policy.substringAfter(':').toLongOrNull()
                }
            }
            val request =
                authorized(Request.Builder().url("$serverUrl/screens/$encodedName")).build()
            http.newCall(request).enqueue(
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
                                post { if (!isDestroyed) onUnauthorized() }
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
                                screenCache.store(name, policy, payload, asOf)
                            }
                            if (it.header("X-Latawiec-Refreshable") != null) {
                                post { swipe.isEnabled = true }
                            }
                            render(payload)
                            it.header("X-Latawiec-Manifest")?.let { seen ->
                                // The chrome changed server-side (a tab
                                // appeared?); refetch once, not per screen.
                                // Compared on main: manifestHash lives there.
                                post {
                                    if (!isDestroyed && manifestApplied &&
                                        seen != manifestHash
                                    ) {
                                        manifestHash = seen
                                        fetchManifest()
                                    }
                                }
                            }
                            if (live) {
                                // A live screen subscribes after its first
                                // render; every app.refresh() lands here.
                                post { if (!isDestroyed && isAttachedToWindow) connect() }
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
                    if (!isDestroyed && isAttachedToWindow &&
                        resumed && screens.lastOrNull() == this
                    ) {
                        fetch()
                    }
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
                { if (!isDestroyed && isAttachedToWindow) retry() },
                reconnectDelayMs,
            )
            reconnectDelayMs = (reconnectDelayMs * 2).coerceAtMost(RECONNECT_DELAY_MAX_MS)
        }

        private fun render(payload: String) {
            reconnectDelayMs = RECONNECT_DELAY_MS
            val data = parseCard(JSONObject(payload))
            post {
                if (!isDestroyed) {
                    divView.setData(data, DivDataTag(name))
                    spinner.visibility = View.GONE
                    swipe.isRefreshing = false
                }
            }
        }
    }

    /**
     * Every enabled provider is asked at once and the first fix wins: GPS
     * gives the best one but indoors it never arrives, where the network
     * provider answers in a second.
     */
    private fun requestFix() {
        // The permission prompt can outlive this activity (a rotation, or
        // process death); without an ask to answer, subscribing would leave
        // every provider listening for the rest of the session.
        val ask = pendingLocation ?: return
        val manager = getSystemService(LocationManager::class.java)
        val providers = manager?.getProviders(true).orEmpty()
        if (manager == null || providers.isEmpty()) {
            deliverLocation("")
            return
        }
        for (provider in providers) {
            val listener = FixListener()
            fixListeners += listener
            try {
                manager.requestLocationUpdates(provider, 0L, 0f, listener, mainLooper)
            } catch (e: SecurityException) {
                Log.w(TAG, "location updates from $provider refused: $e")
            }
        }
        val timeout = Runnable { if (pendingLocation === ask) deliverLocation("") }
        fixTimeout = timeout
        stackHost.postDelayed(timeout, FIX_TIMEOUT_MS)
    }

    /** Leaving the app drops the ask: no listeners, no late empty submit. */
    private fun cancelFix() {
        pendingLocation = null
        fixTimeout?.let { stackHost.removeCallbacks(it) }
        fixTimeout = null
        val manager = getSystemService(LocationManager::class.java)
        for (listener in fixListeners) manager?.removeUpdates(listener)
        fixListeners.clear()
    }

    /** First answer (or the timeout) wins; the rest find nothing pending. */
    private fun deliverLocation(value: String) {
        val ask = pendingLocation ?: return
        cancelFix()
        if (isDestroyed) return
        // A restored ask lost its screen with the old activity, so the fix
        // lands on whichever screen is showing when it arrives.
        (ask.screen ?: screens.lastOrNull())?.setVariable(ask.variable, value)
        if (ask.action != null) submit(ask.action, JSONObject().put(ask.variable, value))
    }

    private inner class FixListener : LocationListener {
        override fun onLocationChanged(location: Location) {
            // Locale.US: a comma as the decimal separator would cut the pair
            // into three numbers on a Polish phone.
            deliverLocation(
                String.format(Locale.US, "%.6f,%.6f", location.latitude, location.longitude),
            )
        }

        // Default methods on modern SDKs, abstract back on API 26-29, where
        // leaving them out crashes the moment the system calls one.
        @Deprecated("Deprecated in Java")
        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit

        override fun onProviderEnabled(provider: String) = Unit

        override fun onProviderDisabled(provider: String) = Unit
    }

    /**
     * Hands the system camera app a file of ours to write into. A device
     * with no camera app at all says so rather than looking broken.
     */
    private fun shoot() {
        val target = photoTarget()
        if (target == null) {
            pendingPickVariable = null
            pendingPickScreen = null
            showError("Could not reach the camera")
            return
        }
        pendingPhotoUri = target
        try {
            takePhoto.launch(target)
        } catch (e: ActivityNotFoundException) {
            Log.w(TAG, "no camera app: $e")
            pendingPickVariable = null
            pendingPickScreen = null
            pendingPhotoUri = null
            showError("This device has no camera")
        }
    }

    /**
     * The server has the bytes now, so our copy is litter. A gallery pick
     * belongs to the user, not to us, and is left alone.
     */
    private fun discardShot(uri: Uri) {
        if (uri.authority != "$packageName.files") return
        val name = uri.lastPathSegment?.substringAfterLast('/') ?: return
        File(File(cacheDir, "camera"), name).delete()
    }

    private fun photoTarget(): Uri? {
        val dir = File(cacheDir, "camera")
        if (!dir.exists() && !dir.mkdirs()) {
            Log.w(TAG, "camera cache directory refused")
            return null
        }
        // A shot whose upload never ran (the app died mid-flight) would
        // otherwise sit in the cache for good.
        val stale = System.currentTimeMillis() - PHOTO_KEEP_MS
        dir.listFiles()?.forEach { if (it.lastModified() < stale) it.delete() }
        return try {
            FileProvider.getUriForFile(
                this,
                "$packageName.files",
                File(dir, "shot-${System.currentTimeMillis()}.jpg"),
            )
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "camera target refused: $e")
            null
        }
    }

    /**
     * Ships the picked photo to the server's @app.upload handler and sets
     * the picker's variable to whatever it returned — the preview and any
     * Submit pick it up from there.
     */
    private fun uploadPicked(uri: Uri, variable: String, target: ScreenView?) {
        val type = contentResolver.getType(uri) ?: "application/octet-stream"
        val name = contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (cursor.moveToFirst() && column >= 0) cursor.getString(column) else null
        } ?: "photo"
        // Streamed, not buffered: the photo flows from the content provider
        // straight into the request on OkHttp's worker thread — a 100 MB
        // original neither fills memory nor stalls the main thread.
        val streamed = object : RequestBody() {
            override fun contentType() = type.toMediaType()

            override fun writeTo(sink: BufferedSink) {
                val input = contentResolver.openInputStream(uri)
                    ?: throw IOException("picked photo vanished")
                input.source().use(sink::writeAll)
            }
        }
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", name, streamed)
            .build()
        val request = authorized(Request.Builder().url("$serverUrl/uploads").post(body)).build()
        http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    discardShot(uri)
                    Log.w(TAG, "upload failed: $e")
                    showError("Upload failed — try again")
                }

                override fun onResponse(call: Call, response: Response) {
                    discardShot(uri)
                    response.use {
                        if (it.code == 401) {
                            stackHost.post { if (!isDestroyed) onUnauthorized() }
                            return
                        }
                        if (!it.isSuccessful) {
                            Log.w(TAG, "upload answered HTTP ${it.code}")
                            showError(
                                if (it.code == 413) {
                                    "That photo is too big"
                                } else {
                                    "Upload failed — try again"
                                },
                            )
                            return
                        }
                        val value = JSONObject(it.body?.string() ?: return).optString("value")
                        stackHost.post {
                            if (!isDestroyed) {
                                (target ?: screens.lastOrNull())
                                    ?.setVariable(variable, value)
                            }
                        }
                    }
                }
            },
        )
    }

    /** The user acted and nothing happened; say so instead of only logging. */
    private fun showError(message: String) {
        stackHost.post {
            if (!isDestroyed) Snackbar.make(stackHost, message, Snackbar.LENGTH_LONG).show()
        }
    }

    /** Every screen and action request carries the token and device context. */
    private fun authorized(builder: Request.Builder): Request.Builder {
        token?.let { builder.header("Authorization", "Bearer $it") }
        builder.header("Accept-Language", LocaleList.getDefault().toLanguageTags())
        builder.header("X-Latawiec-Platform", "android")
        builder.header("X-Latawiec-Timezone", TimeZone.getDefault().id)
        builder.header("X-Latawiec-App-Version", BuildConfig.VERSION_NAME)
        return builder
    }

    /** A rejected token is gone for good; the login screen starts over. */
    private fun onUnauthorized() {
        token = null
        tokenStore.clear()
        // The identity ended, so its cached screens must go with it.
        screenCache.clear()
        val login = loginScreen
        if (login != null) {
            showRoot(login)
        } else {
            Log.w(TAG, "server answered 401 and the manifest names no login screen")
        }
    }

    /** The user chose to leave: token and cached screens go together. */
    private fun signOut(target: String?) {
        token = null
        tokenStore.clear()
        screenCache.clear()
        showRoot(target ?: loginScreen ?: "home")
    }

    private fun parseCard(payload: JSONObject): DivData {
        val environment = DivParsingEnvironment(ParsingErrorLogger.LOG)
        payload.optJSONObject("templates")?.let(environment::parseTemplates)
        return DivData(environment, payload.getJSONObject("card"))
    }

    /**
     * Tabs and theme come from the manifest. A server without the endpoint (or
     * any fetch or parse failure) falls back to the bare single-screen shell
     * on "home".
     */
    private fun fetchManifest() {
        val request = Request.Builder().url("$serverUrl/manifest").build()
        http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    Log.w(TAG, "manifest fetch failed: $e")
                    // Offline boot runs on the last manifest the shell saw.
                    val remembered = screenCache.loadManifest()?.let {
                        try {
                            JSONObject(it)
                        } catch (parse: JSONException) {
                            null
                        }
                    }
                    stackHost.post {
                        if (isDestroyed) return@post
                        // A redeploy blip mid-session must not nuke the
                        // chrome; a cleared hash retries on the next
                        // fingerprint or foreground.
                        if (manifestApplied) {
                            manifestHash = null
                            return@post
                        }
                        // A typed address that never answered once is most
                        // likely a typo; ask again instead of spinning.
                        if (remembered == null && BuildConfig.SERVER_URL.isEmpty()) {
                            askForServer()
                        } else {
                            boot(remembered)
                        }
                    }
                }

                override fun onResponse(call: Call, response: Response) {
                    var fingerprint: String? = null
                    val manifest = response.use {
                        if (it.isSuccessful) {
                            fingerprint = it.header("X-Latawiec-Manifest")
                            try {
                                JSONObject(it.body?.string() ?: "")
                            } catch (e: JSONException) {
                                Log.w(TAG, "manifest is not valid JSON: $e")
                                null
                            }
                        } else {
                            Log.w(TAG, "manifest answered HTTP ${it.code}")
                            null
                        }
                    }
                    stackHost.post {
                        if (isDestroyed) return@post
                        if (manifest == null && manifestApplied) {
                            manifestHash = null
                            return@post
                        }
                        if (manifest != null) manifestHash = fingerprint
                        boot(manifest)
                    }
                }
            },
        )
    }

    /** The deep link that launched the shell waits for the manifest's tabs. */
    private fun boot(manifest: JSONObject?) {
        applyManifest(manifest)
        manifestApplied = true
        pendingDeepLink?.let {
            pendingDeepLink = null
            openDeepLink(it)
        }
    }

    private fun applyManifest(manifest: JSONObject?) {
        loginScreen = manifest?.opt("login") as? String
        if (manifest?.optBoolean("push") == true) enablePush()
        if (manifest != null) {
            devMode = manifest.optBoolean("dev", true)
            // Cached screens may be rendered per locale, so a language
            // change drops them exactly like a version bump.
            val version = manifest.opt("version") as? String
            screenCache.adoptVersion(
                "${version.orEmpty()}|${LocaleList.getDefault().toLanguageTags()}",
            )
            screenCache.storeManifest(manifest.toString())
        }
        val tabs = manifest?.optJSONArray("tabs")
        if (tabs == null || tabs.length() == 0) {
            bottomBar.menu.clear()
            bottomBar.visibility = View.GONE
            // Re-applied mid-session with the same (lack of) tabs: the
            // stack the user is in stays put.
            if (tabRoots.isNotEmpty() || screens.isEmpty()) {
                tabRoots = emptyList()
                showRoot("home")
            }
            return
        }
        val tabScreens = ArrayList<String>(tabs.length())
        val tabTitles = ArrayList<String>(tabs.length())
        val tabIcons = ArrayList<String?>(tabs.length())
        try {
            for (i in 0 until tabs.length()) {
                val tab = tabs.getJSONObject(i)
                tabScreens.add(tab.getString("screen"))
                tabTitles.add(tab.getString("title"))
                tabIcons.add(if (tab.isNull("icon")) null else tab.getString("icon"))
            }
        } catch (e: JSONException) {
            Log.w(TAG, "manifest tabs are malformed: $e")
            bottomBar.menu.clear()
            bottomBar.visibility = View.GONE
            tabRoots = emptyList()
            showRoot("home")
            return
        }
        // The same roots re-applied mid-session must not reset the stack:
        // keep the selection, refresh what the bar shows.
        val sameRoots = tabScreens == tabRoots
        val selected = if (sameRoots) bottomBar.selectedItemId else 0
        // menu.clear() resets the bar's selection, so restoring it below
        // fires a change event — which must not reach the old listener.
        bottomBar.setOnItemSelectedListener(null)
        bottomBar.menu.clear()
        for (i in tabScreens.indices) {
            val item = bottomBar.menu.add(Menu.NONE, i, i, tabTitles[i])
            item.icon = placeholderIcon()
            tabIcons[i]?.let { loadIcon(it, item) }
        }
        val accent = manifest.optJSONObject("theme")?.optString("accent").orEmpty()
        if (accent.isNotEmpty()) tintBar(accent)
        // Selection before the listener: restoring it must not re-navigate.
        bottomBar.selectedItemId = selected
        tabRoots = tabScreens
        bottomBar.setOnItemSelectedListener { item ->
            showRoot(tabScreens[item.itemId])
            true
        }
        // Without this, Material routes a re-tap of the selected item to the
        // selected listener, which would reset the tab.
        bottomBar.setOnItemReselectedListener {}
        bottomBar.visibility = View.VISIBLE
        if (!sameRoots) showRoot(tabScreens[0])
    }

    /**
     * The server registered an @app.device hook; ask to show notifications
     * and hand it this device's token. Token generation does not wait for
     * the permission — that only gates showing the notification.
     */
    private fun enablePush() {
        // Manifest refreshes re-run this; registering once per launch is
        // enough (onNewToken covers rotations).
        if (pushEnabled) return
        if (BuildConfig.FIREBASE_APP_ID.isEmpty()) {
            Log.i(TAG, "server enables push but this build has no Firebase config")
            return
        }
        pushEnabled = true
        if (!askedForNotifications &&
            Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            // Manifest refreshes re-run enablePush; one ask per launch.
            askedForNotifications = true
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 0)
        }
        // onNewToken covers rotations; this covers reinstalls of the same
        // token and a registration POST that failed on an earlier boot.
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { DeviceRegistry.register(this, it) }
            .addOnFailureListener { Log.w(TAG, "push token fetch failed: $it") }
    }

    private fun tintBar(accent: String) {
        val color = try {
            Color.parseColor(accent)
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "theme accent $accent is not a color")
            return
        }
        val tint = ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
            intArrayOf(color, Color.GRAY),
        )
        bottomBar.itemIconTintList = tint
        bottomBar.itemTextColor = tint
    }

    // A menu item without an icon leaves a hole in the bar, so a tab with no
    // manifest icon gets a plain circle the item tint colors like the rest.
    private fun placeholderIcon() = ShapeDrawable(OvalShape()).apply {
        val size = (24 * resources.displayMetrics.density).toInt()
        intrinsicWidth = size
        intrinsicHeight = size
    }

    private fun loadIcon(path: String, item: MenuItem) {
        val request = Request.Builder().url(serverUrl + path).build()
        http.newCall(request).enqueue(
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
                        stackHost.post {
                            if (!isDestroyed) item.icon = BitmapDrawable(resources, bitmap)
                        }
                    }
                }
            },
        )
    }

    /**
     * POSTs the submitted values to the server's action handler and follows the
     * navigation it answers with. The values arrive in the action URL's query:
     * the server wrote them there as DivKit expressions, evaluated at tap time.
     */
    private fun submit(action: String, url: Uri) {
        val values = JSONObject()
        for (key in url.queryParameterNames) {
            if (key != "action") values.put(key, url.getQueryParameter(key))
        }
        submit(action, values)
    }

    private fun submit(action: String, values: JSONObject) {
        val request = authorized(
            Request.Builder()
                .url("$serverUrl/actions/${Uri.encode(action)}")
                .post(values.toString().toRequestBody("application/json".toMediaType())),
        ).build()
        http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    Log.w(TAG, "action $action failed: $e")
                    showError("No connection — try again")
                }

                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        if (it.code == 401) {
                            stackHost.post { if (!isDestroyed) onUnauthorized() }
                            return
                        }
                        if (!it.isSuccessful) {
                            Log.w(TAG, "action $action answered HTTP ${it.code}")
                            showError("Something went wrong — try again")
                            return
                        }
                        val body = JSONObject(it.body?.string() ?: return)
                        // A sign-in action grants the token every later
                        // request authenticates with.
                        (body.opt("token") as? String)?.let { granted ->
                            // A new identity must not inherit the previous
                            // one's cached screens.
                            screenCache.clear()
                            token = granted
                            tokenStore.save(granted)
                        }
                        val navigate = body.opt("navigate")
                        if (navigate is String) {
                            stackHost.post { if (!isDestroyed) showScreen(navigate) }
                        }
                    }
                }
            },
        )
    }

    private inner class LatawiecActionHandler : DivActionHandler() {
        override fun handleAction(
            action: DivAction,
            view: DivViewFacade,
            resolver: ExpressionResolver,
        ): Boolean {
            val url = action.url?.evaluate(resolver)
            if (url != null && handleLatawiec(url)) return true
            return super.handleAction(action, view, resolver)
        }

        /** LoadMore fires a visibility action; DivKit's dispatcher routes
         * those through this DivSightAction overload. */
        override fun handleAction(
            action: DivSightAction,
            view: DivViewFacade,
            resolver: ExpressionResolver,
        ): Boolean {
            val url = action.url?.evaluate(resolver)
            if (url != null && handleLatawiec(url)) return true
            return super.handleAction(action, view, resolver)
        }

        private fun handleLatawiec(url: Uri): Boolean {
            if (url.scheme == "latawiec") {
                when (url.host) {
                    "navigate" -> {
                        val screen = url.getQueryParameter("screen") ?: return false
                        showScreen(screen)
                        return true
                    }

                    "submit" -> {
                        val name = url.getQueryParameter("action") ?: return false
                        submit(name, url)
                        return true
                    }

                    "locate" -> {
                        val variable = url.getQueryParameter("variable") ?: return false
                        pendingLocation = LocationAsk(
                            variable,
                            url.getQueryParameter("action"),
                            screens.lastOrNull(),
                        )
                        val fine = Manifest.permission.ACCESS_FINE_LOCATION
                        val coarse = Manifest.permission.ACCESS_COARSE_LOCATION
                        if (checkSelfPermission(fine) == PackageManager.PERMISSION_GRANTED ||
                            checkSelfPermission(coarse) == PackageManager.PERMISSION_GRANTED
                        ) {
                            requestFix()
                        } else {
                            askLocation.launch(arrayOf(fine, coarse))
                        }
                        return true
                    }

                    "pick" -> {
                        val variable = url.getQueryParameter("variable") ?: return false
                        pendingPickVariable = variable
                        // The value belongs to the screen that asked, even
                        // if the user navigates while the upload runs.
                        pendingPickScreen = screens.lastOrNull()
                        if (url.getQueryParameter("source") == "camera") {
                            shoot()
                        } else {
                            pickMedia.launch(
                                PickVisualMediaRequest(
                                    ActivityResultContracts.PickVisualMedia.ImageOnly,
                                ),
                            )
                        }
                        return true
                    }

                    "signout" -> {
                        signOut(url.getQueryParameter("screen"))
                        return true
                    }

                    "share" -> {
                        val text = url.getQueryParameter("text") ?: return false
                        val send = Intent(Intent.ACTION_SEND)
                            .setType("text/plain")
                            .putExtra(Intent.EXTRA_TEXT, text)
                        startActivity(Intent.createChooser(send, null))
                        return true
                    }

                    "open" -> {
                        val target = url.getQueryParameter("url")?.let(Uri::parse) ?: return false
                        if (target.scheme?.lowercase() !in OPENABLE_SCHEMES) return false
                        try {
                            startActivity(Intent(Intent.ACTION_VIEW, target))
                        } catch (e: ActivityNotFoundException) {
                            // The scheme only: a tel/mailto target is PII.
                            Log.w(TAG, "nothing opens ${target.scheme} links", e)
                            showError("Nothing can open this link")
                        }
                        return true
                    }
                }
            }
            return false
        }
    }
}
