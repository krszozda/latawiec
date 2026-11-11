package io.github.krszozda.latawiec

import android.app.Activity
import android.content.Context
import android.util.Log
import com.yandex.div.core.player.DivPlayerFactory

private const val TAG = "Latawiec"

// A heavy capability ships per build and its implementation lives in a
// source set only that build compiles, so the shell looks the class up by
// name: naming it directly would not compile in a default build. R8
// recognizes a Class.forName on a constant, keeps the class, and rewrites
// the call, so this survives minification.
private const val PLAY_STORE = "io.github.krszozda.latawiec.PlayStore"
private const val MEDIA3_FACTORY = "io.github.krszozda.latawiec.Media3PlayerFactory"

/** Cheap enough for onCreate: it does not build a billing client. */
fun billingBuilt(): Boolean = runCatching { Class.forName(PLAY_STORE) }.isSuccess

/** Present only in a -PwithBilling build; see [StoreFront]. */
fun storeFront(activity: Activity): StoreFront? = try {
    Class.forName(PLAY_STORE)
        .getDeclaredConstructor(Activity::class.java)
        .newInstance(activity) as StoreFront
} catch (e: ReflectiveOperationException) {
    null
} catch (e: LinkageError) {
    Log.w(TAG, "billing is present but unusable: $e")
    null
}

class VideoPlayer(val name: String, val factory: DivPlayerFactory)

/**
 * A -PwithVideo build carries ExoPlayer; a default one does not, and
 * referring to the class directly would not compile there. Reflection
 * is what keeps the two builds one source tree.
 */
fun videoPlayer(context: Context): VideoPlayer = try {
    VideoPlayer(
        "media3",
        Class.forName(MEDIA3_FACTORY)
            .getDeclaredConstructor(Context::class.java)
            .newInstance(context) as DivPlayerFactory,
    )
} catch (e: ReflectiveOperationException) {
    VideoPlayer("system", SystemPlayerFactory())
} catch (e: LinkageError) {
    // The class is there but its libraries are not: a half-shrunk
    // build, which would otherwise crash instead of falling back.
    Log.w(TAG, "Media3 is present but unusable: $e")
    VideoPlayer("system", SystemPlayerFactory())
}
