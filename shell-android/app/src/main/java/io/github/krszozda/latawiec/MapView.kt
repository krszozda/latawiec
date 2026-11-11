package io.github.krszozda.latawiec

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.Log
import android.util.LruCache
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import androidx.core.graphics.toColorInt
import com.yandex.div.core.DivCustomContainerViewAdapter
import com.yandex.div.core.state.DivStatePath
import com.yandex.div.core.view2.Div2View
import com.yandex.div.json.expressions.ExpressionResolver
import com.yandex.div2.DivCustom
import java.io.IOException
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.tan
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject

private const val MAP_TAG = "LatawiecMap"

/** Side of a raster map tile, the size every XYZ server serves. */
private const val TILE = 256

private const val MIN_ZOOM = 1
private const val MAX_ZOOM = 19

/** Bitmaps to hold on to. Four screens' worth of tiles, not sixty-four. */
private const val TILE_CACHE_BYTES = 4 * 1024 * 1024

/**
 * Android has no system map, and Google's SDK would cost about a megabyte
 * against a three-megabyte APK, so the shell draws one itself: raster tiles
 * fetched over the shell's own HTTP client and painted onto a canvas.
 */
@SuppressLint("ViewConstructor")
class MapView(context: Context, private val http: OkHttpClient) : View(context) {

    /**
     * A tile is 256 px of image, laid out as 256 dp: without this a zoom
     * level would cover a different patch of earth on every screen density,
     * and a different one again from iOS.
     */
    private val tileSize = TILE * resources.displayMetrics.density

    private var zoom = 14

    /** Centre of the view in world pixels at the current zoom. */
    private var centerX = 0.0
    private var centerY = 0.0
    private var template = DEFAULT_TILES
    private var markers = emptyList<Marker>()

    /** What the server last asked for, so a re-render can tell a new place
     *  from the same place — and leave a map the user has moved alone. */
    private var placed: Triple<Double, Double, Int>? = null

    private val tiles = object : LruCache<String, Bitmap>(TILE_CACHE_BYTES) {
        override fun sizeOf(key: String, value: Bitmap): Int = value.allocationByteCount
    }
    private val pending = mutableMapOf<String, Call>()

    /** Tiles that answered with something undrawable; asking again every
     *  frame would hammer the tile server for the rest of the session. */
    private val refused = mutableSetOf<String>()

    /** A template the HTTP client will not take at all, remembered so the
     *  refusal is noticed once instead of once per tile. */
    private var brokenTemplate: String? = null

    private val density = resources.displayMetrics.density
    private val pinPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = "#D32F2F".toColorInt() }
    private val pinStroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        style = Paint.Style.STROKE
        strokeWidth = 2f * density
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.BLACK
        textSize = 12f * density
        textAlign = Paint.Align.CENTER
    }
    private val labelHalo = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 12f * density
        textAlign = Paint.Align.CENTER
        style = Paint.Style.STROKE
        strokeWidth = 3f * density
    }
    private val emptyPaint = Paint().apply { color = "#E8EAED".toColorInt() }

    /** Reused: onDraw runs per frame and allocating here would churn. */
    private val tileRect = RectF()

    data class Marker(val latitude: Double, val longitude: Double, val label: String)

    init {
        describe()
    }

    private val drag = GestureDetector(
        context,
        object : GestureDetector.SimpleOnGestureListener() {
            override fun onScroll(
                e1: MotionEvent?,
                e2: MotionEvent,
                distanceX: Float,
                distanceY: Float,
            ): Boolean {
                // The scroll that follows a pinch reports everything the
                // fingers travelled while the detector was starved.
                if (skipNextScroll) {
                    skipNextScroll = false
                    return true
                }
                holdTheGesture()
                centerX += distanceX
                centerY += distanceY
                clampCenter()
                describe()
                invalidate()
                return true
            }

            override fun onDown(e: MotionEvent): Boolean = true
        },
    )

    private var skipNextScroll = false

    private val pinch = ScaleGestureDetector(
        context,
        object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            private var pendingZoom = 0f

            override fun onScale(detector: ScaleGestureDetector): Boolean {
                // Tiles exist at whole zoom levels only, so a pinch is
                // gathered until it adds up to one.
                pendingZoom += ln(detector.scaleFactor.toDouble()).toFloat() / ln(2.0).toFloat()
                val steps = pendingZoom.toInt()
                if (steps != 0) {
                    pendingZoom -= steps
                    holdTheGesture()
                    zoomBy(steps)
                }
                return true
            }
        },
    )

    fun bind(props: JSONObject) {
        val latitude = props.optDouble("latitude", 0.0)
        val longitude = props.optDouble("longitude", 0.0)
        val wanted = props.optInt("zoom", 14).coerceIn(MIN_ZOOM, MAX_ZOOM)
        val source = props.optString("tiles").ifEmpty { DEFAULT_TILES }
        if (source != template) {
            // Another server's tiles are not these tiles.
            template = source
            tiles.evictAll()
            refused.clear()
        }
        // A live screen re-renders on every message; moving the map back
        // under the user's finger each time is not a map.
        val here = Triple(latitude, longitude, wanted)
        if (placed != here) {
            placed = here
            zoom = wanted
            centerX = longitudeToX(longitude, zoom, tileSize)
            centerY = latitudeToY(latitude, zoom, tileSize)
            clampCenter()
        }
        markers = buildList {
            val pins = props.optJSONArray("markers") ?: return@buildList
            for (i in 0 until pins.length()) {
                val pin = pins.optJSONObject(i) ?: continue
                add(
                    Marker(
                        pin.optDouble("latitude", 0.0),
                        pin.optDouble("longitude", 0.0),
                        pin.optString("label"),
                    ),
                )
            }
        }
        describe()
        invalidate()
    }

    /** The map is all canvas; this is the only handle a test — or a screen
     *  reader — has on where it is looking. */
    private fun describe() {
        val latitude = yToLatitude(centerY, zoom, tileSize)
        val longitude = xToLongitude(centerX, zoom, tileSize)
        contentDescription = "map %.4f,%.4f z%d".format(latitude, longitude, zoom)
    }

    /** Once the map has the gesture, no ancestor may steal it mid-pan. A
     *  Gallery keeps its scrolling until then, so a feed with a map in it
     *  still scrolls past it. */
    private fun holdTheGesture() {
        parent?.requestDisallowInterceptTouchEvent(true)
    }

    private fun zoomBy(steps: Int) {
        val target = (zoom + steps).coerceIn(MIN_ZOOM, MAX_ZOOM)
        if (target == zoom) return
        val scale = 2.0.pow(target - zoom)
        centerX *= scale
        centerY *= scale
        zoom = target
        clampCenter()
        describe()
        invalidate()
    }

    /** Panning past the poles would show bare canvas; east and west wrap. */
    private fun clampCenter() {
        val world = tileSize * 2.0.pow(zoom)
        centerY = if (world <= height) {
            // The whole world is shorter than the view: centre it rather
            // than pinning it to an edge.
            world / 2
        } else {
            centerY.coerceIn(height / 2.0, world - height / 2.0)
        }
        centerX = ((centerX % world) + world) % world
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        val wasPinching = pinch.isInProgress
        pinch.onTouchEvent(event)
        // A pinch moves both fingers; letting the drag see it too would
        // send the map sliding away under them.
        if (!pinch.isInProgress) {
            if (wasPinching) skipNextScroll = true
            drag.onTouchEvent(event)
        }
        return true
    }

    override fun onDraw(canvas: Canvas) {
        val left = centerX - width / 2.0
        val top = centerY - height / 2.0
        val span = 2.0.pow(zoom).toInt()
        val firstX = floor(left / tileSize).toInt()
        val firstY = floor(top / tileSize).toInt()

        var y = firstY
        while (y * tileSize < top + height) {
            var x = firstX
            while (x * tileSize < left + width) {
                val offsetX = (x * tileSize - left).toFloat()
                val offsetY = (y * tileSize - top).toFloat()
                // The world wraps east to west; the poles do not.
                val wrapped = ((x % span) + span) % span
                if (y in 0 until span) {
                    draw(canvas, wrapped, y, offsetX, offsetY)
                } else {
                    canvas.drawRect(
                        offsetX, offsetY, offsetX + tileSize, offsetY + tileSize, emptyPaint,
                    )
                }
                x++
            }
            y++
        }
        drawMarkers(canvas, left, top)
    }

    private fun draw(canvas: Canvas, x: Int, y: Int, offsetX: Float, offsetY: Float) {
        val key = "$template|$zoom/$x/$y"
        val tile = tiles.get(key)
        if (tile == null) {
            canvas.drawRect(offsetX, offsetY, offsetX + tileSize, offsetY + tileSize, emptyPaint)
            request(key, x, y)
            return
        }
        canvas.drawBitmap(tile, null, tileRect.apply {
            set(offsetX, offsetY, offsetX + tileSize, offsetY + tileSize)
        }, null)
    }

    private fun request(key: String, x: Int, y: Int) {
        if (key in pending || key in refused || template == brokenTemplate) return
        val url = template
            .replace("{z}", zoom.toString())
            .replace("{x}", x.toString())
            .replace("{y}", y.toString())
        val request = try {
            Request.Builder()
                .url(url)
                // OpenStreetMap's policy asks who is calling; an app on its
                // own tile server can say whatever it likes.
                .header("User-Agent", "Latawiec-Shell")
                .build()
        } catch (e: IllegalArgumentException) {
            // The client throws on anything that is not an http(s) URL, and
            // this runs while a frame is being drawn: a server that sends a
            // broken template would otherwise take the app down with it.
            Log.w(MAP_TAG, "tile template $template is not a URL: $e")
            brokenTemplate = template
            return
        }
        val call = http.newCall(request)
        pending[key] = call
        call.enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (call.isCanceled()) return
                    Log.w(MAP_TAG, "tile $key did not load: $e")
                    // A dropped connection may well work next time.
                    post { pending.remove(key) }
                }

                override fun onResponse(call: Call, response: Response) {
                    val code = response.code
                    val bitmap = response.use {
                        it.body?.byteStream()?.let(BitmapFactory::decodeStream)
                    }
                    post {
                        pending.remove(key)
                        if (bitmap != null) {
                            tiles.put(key, bitmap)
                            invalidate()
                        } else {
                            // A 404 or an error page: the same answer is
                            // waiting next frame, so stop asking.
                            Log.w(MAP_TAG, "tile $key answered HTTP $code with no image")
                            refused.add(key)
                        }
                    }
                }
            },
        )
    }

    private fun drawMarkers(canvas: Canvas, left: Double, top: Double) {
        val world = tileSize * 2.0.pow(zoom)
        for (pin in markers) {
            val y = (latitudeToY(pin.latitude, zoom, tileSize) - top).toFloat()
            val worldX = longitudeToX(pin.longitude, zoom, tileSize)
            // The tiles wrap around the date line, so the pin is drawn on
            // whichever copy of the world is on screen.
            for (copy in -1..1) {
                val screenX = (worldX + copy * world - left).toFloat()
                if (screenX < -PIN_RADIUS * density || screenX > width + PIN_RADIUS * density) {
                    continue
                }
                canvas.drawCircle(screenX, y, PIN_RADIUS * density, pinPaint)
                canvas.drawCircle(screenX, y, PIN_RADIUS * density, pinStroke)
                if (pin.label.isNotEmpty()) {
                    canvas.drawText(pin.label, screenX, y - 12f * density, labelHalo)
                    canvas.drawText(pin.label, screenX, y - 12f * density, labelPaint)
                }
            }
        }
    }

    override fun onDetachedFromWindow() {
        pending.values.forEach(Call::cancel)
        pending.clear()
        super.onDetachedFromWindow()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        clampCenter()
        describe()
    }
}

private const val PIN_RADIUS = 7f
private const val DEFAULT_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

/** Web Mercator, the projection every XYZ tile server is cut to. */
internal fun longitudeToX(longitude: Double, zoom: Int, tileSize: Float): Double =
    (longitude + 180.0) / 360.0 * tileSize * 2.0.pow(zoom)

internal fun latitudeToY(latitude: Double, zoom: Int, tileSize: Float): Double {
    val radians = Math.toRadians(latitude.coerceIn(-85.05112878, 85.05112878))
    val merc = ln(tan(radians) + 1.0 / cos(radians))
    return (1.0 - merc / Math.PI) / 2.0 * tileSize * 2.0.pow(zoom)
}

internal fun yToLatitude(y: Double, zoom: Int, tileSize: Float): Double {
    val n = Math.PI - 2.0 * Math.PI * y / (tileSize * 2.0.pow(zoom))
    return Math.toDegrees(kotlin.math.atan(kotlin.math.sinh(n)))
}

internal fun xToLongitude(x: Double, zoom: Int, tileSize: Float): Double =
    x / (tileSize * 2.0.pow(zoom)) * 360.0 - 180.0

/**
 * Hands DivKit the map view for the DSL's Map, which it knows only as a
 * custom block.
 */
class MapViewAdapter(private val http: OkHttpClient) : DivCustomContainerViewAdapter {
    override fun isCustomTypeSupported(type: String): Boolean = type == "latawiec_map"

    override fun createView(
        div: DivCustom,
        divView: Div2View,
        resolver: ExpressionResolver,
        path: DivStatePath,
    ): View = MapView(divView.context, http)

    override fun bindView(
        view: View,
        div: DivCustom,
        divView: Div2View,
        resolver: ExpressionResolver,
        path: DivStatePath,
    ) {
        (view as? MapView)?.bind(div.customProps ?: JSONObject())
    }

    override fun release(view: View, div: DivCustom) = Unit
}
