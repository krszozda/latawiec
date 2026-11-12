package io.github.krszozda.latawiec

import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.LocaleList
import android.os.Looper
import android.provider.OpenableColumns
import androidx.core.content.edit
import java.io.IOException
import java.util.TimeZone
import java.util.concurrent.TimeUnit
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Headers
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okio.BufferedSink
import okio.source
import org.json.JSONObject

/** How often a held-open socket proves it is still there. */
private const val SOCKET_PING_SECONDS = 20L

/** What the server answered, read in full and handed over on the main thread. */
internal sealed interface Reply {

    /** A 2xx, with the body already read and the headers it arrived with. */
    data class Ok(val body: String, val headers: Headers) : Reply

    /** The token was refused: whoever sent it has no identity any more. */
    data object Unauthorized : Reply

    /** Any other answer: a 404, a 500, a proxy's error page mid-redeploy. */
    data class Refused(val code: Int) : Reply

    /** Nothing answered: no network, no server, or a connection that dropped. */
    data class Unreachable(val cause: IOException) : Reply
}

/**
 * The shell's side of the protocol: where the server is, the token the
 * activity's requests carry, and the three requests the activity makes on its
 * own behalf. Those three answer small, so the body is read here and the
 * [Reply] handed to the main thread, where the shell can act on it. A screen,
 * a tab icon or a map tile streams off [http] instead, which is what keeps a
 * disk write and a bitmap decode off that thread.
 *
 * Push registration is the one request that does not come from here: it runs
 * from a service, with no activity to hold. See [DeviceRegistry].
 */
internal class Server(private val host: MainActivity) {

    val http = OkHttpClient()

    /**
     * Pings keep a live screen honest: a socket that died without a close —
     * a dropped network, a NAT or proxy timeout — reports nothing by
     * itself, so without them the screen sits on its last render forever
     * and the reconnect backoff never starts.
     *
     * Its own client, because pingInterval also pings every HTTP/2
     * connection the client makes and fails it on a missing pong; screens,
     * actions, uploads and map tiles have their own timeouts and want no
     * part of that. newBuilder shares the pool and dispatcher, so this
     * costs nothing.
     */
    val sockets = http.newBuilder()
        .pingInterval(SOCKET_PING_SECONDS, TimeUnit.SECONDS)
        .build()

    private val config = host.getSharedPreferences("latawiec-config", Context.MODE_PRIVATE)

    /**
     * The address the user typed on a first start, which only a build with no
     * baked-in URL — the generic try-it-out APK — ever asks for. [url] reads
     * it once, so a newly typed one takes effect on the next start.
     */
    var typedAddress: String
        get() = config.getString("serverUrl", "").orEmpty()
        set(value) = config.edit { putString("serverUrl", value) }

    // Instrumentation tests point the shell at a per-test server. Debug-only:
    // the activity is exported, so in a release build any app could repoint
    // the shell at its own server with this extra.
    val url: String by lazy {
        host.intent.getStringExtra("serverUrl").takeIf { BuildConfig.DEBUG }
            ?: BuildConfig.SERVER_URL.ifEmpty { typedAddress }
    }

    private val tokens = TokenStore(host)
    private var token: String? = tokens.load()

    // Replies come off OkHttp's threads; the shell meets them on its own.
    private val main = Handler(Looper.getMainLooper())

    /** Every screen and action request carries the token and device context. */
    fun authorized(builder: Request.Builder): Request.Builder {
        token?.let { builder.header("Authorization", "Bearer $it") }
        builder.header("Accept-Language", LocaleList.getDefault().toLanguageTags())
        builder.header("X-Latawiec-Platform", "android")
        builder.header("X-Latawiec-Timezone", TimeZone.getDefault().id)
        builder.header("X-Latawiec-App-Version", BuildConfig.VERSION_NAME)
        return builder
    }

    /**
     * A sign-in granted a token: it travels on every later request, and it
     * outlives the process it was granted to.
     */
    fun remember(granted: String) {
        token = granted
        tokens.save(granted)
    }

    /** The token was refused, or the user signed out: it is gone for good. */
    fun forget() {
        token = null
        tokens.clear()
    }

    /**
     * The chrome. It carries no token, since the manifest is what names the
     * login screen — a shell with no identity yet still has to find it.
     */
    fun manifest(answered: (Reply) -> Unit) {
        send(Request.Builder().url("$url/manifest").build(), answered)
    }

    /** Runs the handler the server registered as @app.action([action]). */
    fun act(action: String, values: JSONObject, answered: (Reply) -> Unit) {
        send(
            authorized(
                Request.Builder()
                    .url("$url/actions/${Uri.encode(action)}")
                    .post(values.toString().toRequestBody("application/json".toMediaType())),
            ).build(),
            answered,
        )
    }

    /** Ships a picked image to the server's @app.upload handler. */
    fun upload(uri: Uri, answered: (Reply) -> Unit) {
        val resolver = host.contentResolver
        val type = resolver.getType(uri) ?: "application/octet-stream"
        val name = resolver.query(uri, null, null, null, null)?.use { cursor ->
            val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (cursor.moveToFirst() && column >= 0) cursor.getString(column) else null
        } ?: "photo"
        // Streamed, not buffered: the photo flows from the content provider
        // straight into the request on OkHttp's worker thread — a 100 MB
        // original neither fills memory nor stalls the main thread.
        val streamed = object : RequestBody() {
            override fun contentType() = type.toMediaType()

            override fun writeTo(sink: BufferedSink) {
                val input = resolver.openInputStream(uri)
                    ?: throw IOException("picked photo vanished")
                input.source().use(sink::writeAll)
            }
        }
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", name, streamed)
            .build()
        send(authorized(Request.Builder().url("$url/uploads").post(body)).build(), answered)
    }

    private fun send(request: Request, answered: (Reply) -> Unit) {
        http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    main.post { answered(Reply.Unreachable(e)) }
                }

                override fun onResponse(call: Call, response: Response) {
                    val reply = response.use {
                        when {
                            it.code == 401 -> Reply.Unauthorized
                            !it.isSuccessful -> Reply.Refused(it.code)
                            // Read here, on OkHttp's thread: the body is a
                            // stream that closes with the response.
                            else -> Reply.Ok(it.body?.string().orEmpty(), it.headers)
                        }
                    }
                    main.post { answered(reply) }
                }
            },
        )
    }
}
