package io.github.krszozda.latawiec

import android.os.Bundle
import android.util.Log
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.widget.FrameLayout
import androidx.appcompat.app.AppCompatActivity
import com.yandex.div.DivDataTag
import com.yandex.div.core.Div2Context
import com.yandex.div.core.DivConfiguration
import com.yandex.div.core.view2.Div2View
import com.yandex.div.data.DivParsingEnvironment
import com.yandex.div.json.ParsingErrorLogger
import com.yandex.div.picasso.PicassoDivImageLoader
import com.yandex.div2.DivData
import okhttp3.OkHttpClient
import okhttp3.Request
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val configuration = DivConfiguration.Builder(PicassoDivImageLoader(this)).build()
        divView = Div2View(Div2Context(this, configuration))
        setContentView(divView, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
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
     */
    private fun connect(name: String) {
        val url = "${BuildConfig.SERVER_URL.replaceFirst("http", "ws")}/ws/screens/$name"
        socket = http.newWebSocket(
            Request.Builder().url(url).build(),
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    val data = parseCard(JSONObject(text))
                    divView.post { divView.setData(data, DivDataTag(name)) }
                }

                // OkHttp does not finish the close handshake by itself: without this
                // close() call onClosed never fires and the reload loop stalls.
                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(1000, null)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    reconnect(name)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.w(TAG, "socket to $url failed: $t")
                    reconnect(name)
                }
            },
        )
    }

    private fun reconnect(name: String) {
        divView.postDelayed({ if (!isDestroyed) connect(name) }, RECONNECT_DELAY_MS)
    }

    private fun parseCard(payload: JSONObject): DivData {
        val environment = DivParsingEnvironment(ParsingErrorLogger.LOG)
        payload.optJSONObject("templates")?.let(environment::parseTemplates)
        return DivData(environment, payload.getJSONObject("card"))
    }
}
