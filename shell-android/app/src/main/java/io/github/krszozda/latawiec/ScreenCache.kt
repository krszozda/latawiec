package io.github.krszozda.latawiec

import android.content.Context
import android.util.Log
import androidx.core.content.edit
import java.io.File
import java.security.MessageDigest
import org.json.JSONObject

private const val TAG = "Latawiec"

/**
 * Last-known screens on disk, keyed by screen path and invalidated as a
 * whole when the server's manifest version changes. Each file starts with
 * the screen's cache policy on its own line, so a "static" hit can skip
 * revalidation until the version moves.
 */
class ScreenCache(context: Context) {

    private val dir = File(context.filesDir, "screens")
    private val prefs = context.getSharedPreferences("latawiec-cache", Context.MODE_PRIVATE)

    /** The last manifest the shell saw; offline starts boot from it. */
    fun storeManifest(manifest: String) {
        prefs.edit { putString("manifest", manifest) }
    }

    fun loadManifest(): String? = prefs.getString("manifest", null)

    /**
     * Bumped by every wipe: a store captured before it must not land, or an
     * in-flight response would re-poison the cache a sign-out cleared.
     */
    var generation = 0
        private set

    /** Drops every cached screen now (sign-out, identity change). */
    fun clear() {
        dir.deleteRecursively()
        generation++
    }

    /** Drops every cached screen when the served version changes. */
    fun adoptVersion(version: String?) {
        val known = prefs.getString("version", null)
        if (version == known) return
        dir.deleteRecursively()
        generation++
        prefs.edit { putString("version", version) }
    }

    fun load(name: String): Entry? {
        val file = file(name)
        if (!file.exists()) return null
        return try {
            val content = file.readText()
            val split = content.indexOf('\n')
            val entry =
                Entry(policy = content.substring(0, split), payload = content.substring(split + 1))
            // A truncated write must land here, not crash the render loop.
            JSONObject(entry.payload)
            entry
        } catch (e: Exception) {
            Log.w(TAG, "cached screen $name did not read: $e")
            file.delete()
            null
        }
    }

    fun store(name: String, policy: String, payload: String, asOf: Int = generation) {
        if (asOf != generation) return
        try {
            dir.mkdirs()
            val target = file(name)
            val staging = File(dir, target.name + ".tmp")
            staging.writeText("$policy\n$payload")
            if (!staging.renameTo(target)) {
                staging.delete()
                Log.w(TAG, "screen $name was not cached: rename failed")
            }
        } catch (e: Exception) {
            Log.w(TAG, "screen $name was not cached: $e")
        }
    }

    // Screen paths may hold slashes and params; the digest makes a safe name.
    private fun file(name: String): File {
        val digest = MessageDigest.getInstance("SHA-256").digest(name.toByteArray())
        return File(dir, digest.joinToString("") { "%02x".format(it) } + ".json")
    }

    data class Entry(val policy: String, val payload: String)
}
