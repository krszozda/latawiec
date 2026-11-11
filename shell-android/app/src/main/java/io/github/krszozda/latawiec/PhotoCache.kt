package io.github.krszozda.latawiec

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.core.content.FileProvider
import java.io.File

private const val TAG = "Latawiec"

/** How long a camera shot stays in the cache before it is swept. */
private const val PHOTO_KEEP_MS = 24 * 60 * 60 * 1000L

/**
 * Where the system camera app writes a shot, and what becomes of it after
 * the upload. The file is ours, not the user's: it exists only to give the
 * picture somewhere to land on its way to the server.
 */
class PhotoCache(private val context: Context) {

    private val dir = File(context.cacheDir, "camera")

    /** A file of ours for the camera app to fill, or null if it refused. */
    fun target(): Uri? {
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
                context,
                "${context.packageName}.files",
                File(dir, "shot-${System.currentTimeMillis()}.jpg"),
            )
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "camera target refused: $e")
            null
        }
    }

    /**
     * The server has the bytes now, so our copy is litter. A gallery pick
     * belongs to the user, not to us, and is left alone.
     */
    fun discard(uri: Uri) {
        if (uri.authority != "${context.packageName}.files") return
        val name = uri.lastPathSegment?.substringAfterLast('/') ?: return
        File(dir, name).delete()
    }
}
