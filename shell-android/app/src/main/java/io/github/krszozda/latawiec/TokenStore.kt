package io.github.krszozda.latawiec

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import androidx.core.content.edit
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private const val TAG = "Latawiec"
private const val KEY_ALIAS = "latawiec-token"
private const val PREFS = "latawiec"
private const val PREF_TOKEN = "token"
private const val GCM_TAG_BITS = 128

/**
 * Persists the auth token encrypted with an Android Keystore key, so the
 * plaintext never touches disk. Any read or crypto failure clears the entry:
 * the user signs in again, which beats crashing or sending a stale token.
 */
class TokenStore(context: Context) {

    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): String? {
        val stored = prefs.getString(PREF_TOKEN, null) ?: return null
        return try {
            val parts = stored.split(":", limit = 2)
            val iv = Base64.decode(parts[0], Base64.NO_WRAP)
            val encrypted = Base64.decode(parts[1], Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(GCM_TAG_BITS, iv))
            String(cipher.doFinal(encrypted))
        } catch (e: Exception) {
            Log.w(TAG, "stored token did not decrypt: $e")
            clear()
            null
        }
    }

    fun save(token: String) {
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key())
            val iv = Base64.encodeToString(cipher.iv, Base64.NO_WRAP)
            val encrypted = Base64.encodeToString(cipher.doFinal(token.toByteArray()), Base64.NO_WRAP)
            prefs.edit { putString(PREF_TOKEN, "$iv:$encrypted") }
        } catch (e: Exception) {
            Log.w(TAG, "token was not saved: $e")
        }
    }

    fun clear() {
        prefs.edit { remove(PREF_TOKEN) }
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry)?.let {
            return it.secretKey
        }
        val generator = KeyGenerator.getInstance("AES", "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }
}
