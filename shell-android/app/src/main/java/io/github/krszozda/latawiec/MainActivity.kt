package io.github.krszozda.latawiec

import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.widget.FrameLayout
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.yandex.div.DivDataTag
import com.yandex.div.core.Div2Context
import com.yandex.div.core.DivActionHandler
import com.yandex.div.core.DivConfiguration
import com.yandex.div.core.DivViewFacade
import com.yandex.div.core.view2.Div2View
import com.yandex.div.data.DivParsingEnvironment
import com.yandex.div.json.ParsingErrorLogger
import com.yandex.div.json.expressions.ExpressionResolver
import com.yandex.div.picasso.PicassoDivImageLoader
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
import org.json.JSONObject

private const val TAG = "Latawiec"
private const val RECONNECT_DELAY_MS = 1_000L

class MainActivity : AppCompatActivity() {

    private val http = OkHttpClient()
    private lateinit var divView: Div2View
    private var socket: WebSocket? = null

    /** Navigation history; the screen on top is the one on display. */
    private val screenStack = ArrayDeque<String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val configuration = DivConfiguration.Builder(PicassoDivImageLoader(this))
            .actionHandler(LatawiecActionHandler())
            .build()
        divView = Div2View(Div2Context(this, configuration))
        setContentView(divView, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (screenStack.size > 1) {
                        screenStack.removeLast()
                        connect(screenStack.last())
                    } else {
                        finish()
                    }
                }
            },
        )

        screenStack.addLast("home")
        connect("home")
    }

    override fun onDestroy() {
        socket?.cancel()
        super.onDestroy()
    }

    /**
     * The screen arrives over this socket on connect. The server holds it open;
     * when it restarts (`uvicorn --reload` on every code change) the socket drops
     * and the reconnect delivers the fresh screen — that is the live-reload loop.
     *
     * Callbacks of a superseded socket can still fire after navigation (cancel()
     * itself triggers onFailure), so each one acts only when its webSocket is
     * still the one in the `socket` field.
     */
    private fun connect(name: String) {
        socket?.cancel()
        val url = "${BuildConfig.SERVER_URL.replaceFirst("http", "ws")}/ws/screens/$name"
        socket = http.newWebSocket(
            Request.Builder().url(url).build(),
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    val data = parseCard(JSONObject(text))
                    divView.post {
                        if (webSocket == socket) {
                            divView.setData(data, DivDataTag(name))
                        }
                    }
                }

                // OkHttp does not finish the close handshake by itself: without this
                // close() call onClosed never fires and the reload loop stalls.
                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(1000, null)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    if (webSocket == socket) reconnect(name)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.w(TAG, "socket to $url failed: $t")
                    if (webSocket == socket) reconnect(name)
                }
            },
        )
    }

    private fun reconnect(name: String) {
        divView.postDelayed(
            { if (!isDestroyed && name == screenStack.lastOrNull()) connect(name) },
            RECONNECT_DELAY_MS,
        )
    }

    private fun parseCard(payload: JSONObject): DivData {
        val environment = DivParsingEnvironment(ParsingErrorLogger.LOG)
        payload.optJSONObject("templates")?.let(environment::parseTemplates)
        return DivData(environment, payload.getJSONObject("card"))
    }

    private fun showScreen(name: String) {
        // A double-tap would stack the same screen twice and break back.
        if (name != screenStack.lastOrNull()) {
            screenStack.addLast(name)
            connect(name)
        }
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
        val request = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/actions/${Uri.encode(action)}")
            .post(values.toString().toRequestBody("application/json".toMediaType()))
            .build()
        http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    Log.w(TAG, "action $action failed: $e")
                }

                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        if (!it.isSuccessful) {
                            Log.w(TAG, "action $action answered HTTP ${it.code}")
                            return
                        }
                        val navigate = JSONObject(it.body?.string() ?: return).opt("navigate")
                        if (navigate is String) {
                            divView.post { if (!isDestroyed) showScreen(navigate) }
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
