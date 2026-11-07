package io.github.krszozda.latawiec

import android.content.res.ColorStateList
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.ShapeDrawable
import android.graphics.drawable.shapes.OvalShape
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.snackbar.Snackbar
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
import java.io.IOException
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONException
import org.json.JSONObject

private const val TAG = "Latawiec"
private const val RECONNECT_DELAY_MS = 1_000L
private const val RECONNECT_DELAY_MAX_MS = 30_000L
private const val PUSH_ANIMATION_MS = 250L

/** The server's WebSocket close code for a missing or rejected token. */
private const val NOT_AUTHORIZED = 4401

class MainActivity : AppCompatActivity() {

    private val http = OkHttpClient()

    // Instrumentation tests point the shell at a per-test server. Debug-only:
    // the activity is exported, so in a release build any app could repoint
    // the shell at its own server with this extra.
    private val serverUrl by lazy {
        intent.getStringExtra("serverUrl").takeIf { BuildConfig.DEBUG } ?: BuildConfig.SERVER_URL
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

        fetchManifest()
    }

    override fun onDestroy() {
        screens.forEach(ScreenView::stop)
        super.onDestroy()
    }

    /** Tab roots replace the whole history: system back on one exits the app. */
    private fun showRoot(name: String) {
        screens.forEach {
            it.stop()
            stackHost.removeView(it)
        }
        screens.clear()
        push(name, animated = false)
    }

    private fun showScreen(name: String) {
        // A double-tap would stack the same screen twice and break back.
        if (name != screens.lastOrNull()?.name) push(name, animated = true)
    }

    private fun push(name: String, animated: Boolean) {
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
        leaving.animate()
            .translationX(stackHost.width.toFloat())
            .setDuration(PUSH_ANIMATION_MS)
            .withEndAction { stackHost.removeView(leaving) }
    }

    /**
     * One screen of the stack: its own DivView, spinner, and transport. In dev
     * every stacked screen keeps its socket, so the whole stack live-reloads;
     * in production the screen renders from the cache and revalidates.
     */
    private inner class ScreenView(val name: String) : FrameLayout(this@MainActivity) {

        private val divView = Div2View(div2Context)
        private val spinner = ProgressBar(context)
        private var socket: WebSocket? = null
        private var reconnectDelayMs = RECONNECT_DELAY_MS

        init {
            addView(divView, LayoutParams(MATCH_PARENT, MATCH_PARENT))
            addView(spinner, LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.CENTER))
        }

        fun start() {
            if (devMode) connect() else fetch()
        }

        fun stop() {
            socket?.cancel()
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
            val url = "${serverUrl.replaceFirst("http", "ws")}/ws/screens/$name"
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
            val cached = screenCache.load(name)
            if (cached != null) {
                render(cached.payload)
                if (cached.policy == "static") return
            }
            val request = authorized(Request.Builder().url("$serverUrl/screens/$name")).build()
            http.newCall(request).enqueue(
                object : Callback {
                    override fun onFailure(call: Call, e: IOException) {
                        // With a cached copy on screen this is offline mode; a
                        // blank screen keeps retrying on the socket's backoff.
                        Log.w(TAG, "screen $name fetch failed: $e")
                        if (cached == null) later { fetch() }
                    }

                    override fun onResponse(call: Call, response: Response) {
                        response.use {
                            if (it.code == 401) {
                                post { if (!isDestroyed) onUnauthorized() }
                                return
                            }
                            if (!it.isSuccessful) {
                                Log.w(TAG, "screen $name answered HTTP ${it.code}")
                                if (cached == null) later { fetch() }
                                return
                            }
                            val payload = it.body?.string() ?: return
                            val header = it.header("Cache-Control").orEmpty()
                            val policy = when {
                                "no-store" in header -> "no-store"
                                "immutable" in header -> "static"
                                else -> "swr"
                            }
                            if (policy != "no-store") screenCache.store(name, policy, payload)
                            render(payload)
                        }
                    }
                },
            )
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
                }
            }
        }
    }

    /** The user acted and nothing happened; say so instead of only logging. */
    private fun showError(message: String) {
        stackHost.post {
            if (!isDestroyed) Snackbar.make(stackHost, message, Snackbar.LENGTH_LONG).show()
        }
    }

    private fun authorized(builder: Request.Builder): Request.Builder {
        token?.let { builder.header("Authorization", "Bearer $it") }
        return builder
    }

    /** A rejected token is gone for good; the login screen starts over. */
    private fun onUnauthorized() {
        token = null
        tokenStore.clear()
        val login = loginScreen
        if (login != null) {
            showRoot(login)
        } else {
            Log.w(TAG, "server answered 401 and the manifest names no login screen")
        }
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
                    stackHost.post { if (!isDestroyed) applyManifest(remembered) }
                }

                override fun onResponse(call: Call, response: Response) {
                    val manifest = response.use {
                        if (it.isSuccessful) {
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
                    stackHost.post { if (!isDestroyed) applyManifest(manifest) }
                }
            },
        )
    }

    private fun applyManifest(manifest: JSONObject?) {
        loginScreen = manifest?.opt("login") as? String
        if (manifest != null) {
            devMode = manifest.optBoolean("dev", true)
            screenCache.adoptVersion(manifest.opt("version") as? String)
            screenCache.storeManifest(manifest.toString())
        }
        val tabs = manifest?.optJSONArray("tabs")
        if (tabs == null || tabs.length() == 0) {
            showRoot("home")
            return
        }
        val tabScreens = ArrayList<String>(tabs.length())
        try {
            for (i in 0 until tabs.length()) {
                val tab = tabs.getJSONObject(i)
                tabScreens.add(tab.getString("screen"))
                val item = bottomBar.menu.add(Menu.NONE, i, i, tab.getString("title"))
                item.icon = placeholderIcon()
                if (!tab.isNull("icon")) loadIcon(tab.getString("icon"), item)
            }
        } catch (e: JSONException) {
            Log.w(TAG, "manifest tabs are malformed: $e")
            bottomBar.menu.clear()
            showRoot("home")
            return
        }
        val accent = manifest.optJSONObject("theme")?.optString("accent").orEmpty()
        if (accent.isNotEmpty()) tintBar(accent)
        bottomBar.selectedItemId = 0
        bottomBar.setOnItemSelectedListener { item ->
            showRoot(tabScreens[item.itemId])
            true
        }
        // Without this, Material routes a re-tap of the selected item to the
        // selected listener, which would reset the tab.
        bottomBar.setOnItemReselectedListener {}
        bottomBar.visibility = View.VISIBLE
        showRoot(tabScreens[0])
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
            if (url != null && url.scheme == "latawiec") {
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
                }
            }
            return super.handleAction(action, view, resolver)
        }
    }
}
