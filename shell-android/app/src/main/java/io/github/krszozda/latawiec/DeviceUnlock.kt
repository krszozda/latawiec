package io.github.krszozda.latawiec

import android.app.Activity
import android.app.KeyguardManager
import android.content.Intent
import android.hardware.biometrics.BiometricManager.Authenticators.BIOMETRIC_WEAK
import android.hardware.biometrics.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal
import android.util.Log
import androidx.annotation.RequiresApi

private const val TAG = "Latawiec"

/** Both shells word it the same way, so the docs can promise it. */
private const val NO_LOCK = "This device has no lock set up"

/**
 * The device's own check — a fingerprint, a face, or the passcode — in
 * front of whatever asked for it. It gates a tap, not the server: what it
 * guards runs exactly as it would have, once the check passes.
 */
class DeviceUnlock(private val activity: Activity) {

    private var signal: CancellationSignal? = null

    /**
     * Runs the check. [passed] gets the tap through and [failed] carries
     * what to tell the user. Before API 29 BiometricPrompt has no passcode
     * fallback, so the lock screen itself is the prompt and [confirm] gets
     * the intent that shows it — its result is the caller's to handle.
     */
    fun ask(
        reason: String,
        passed: () -> Unit,
        confirm: (Intent) -> Unit,
        failed: (String) -> Unit,
    ) {
        // A fingerprint cannot be enrolled without a PIN behind it, so this
        // one question answers for every method at once — and answers it
        // before a prompt appears, which error codes cannot: asking for
        // biometrics and the passcode together reports "no fingerprints"
        // when the truth is that the device has no lock at all.
        val keyguard = activity.getSystemService(KeyguardManager::class.java)
        if (keyguard == null || !keyguard.isDeviceSecure) {
            failed(NO_LOCK)
            return
        }
        if (Build.VERSION.SDK_INT >= 29) {
            prompt(reason, passed, failed)
            return
        }
        // The platform points at BiometricPrompt instead, which is the
        // branch above — and it only has a passcode fallback from API 29.
        // Below that, this intent is the whole of what there is.
        @Suppress("DEPRECATION")
        val intent = keyguard.createConfirmDeviceCredentialIntent(reason, null)
        if (intent == null) failed(NO_LOCK) else confirm(intent)
    }

    /** Leaving the app takes the prompt with it. */
    fun cancel() {
        signal?.cancel()
        signal = null
    }

    @RequiresApi(29)
    private fun prompt(reason: String, passed: () -> Unit, failed: (String) -> Unit) {
        val prompt = BiometricPrompt.Builder(activity)
            .setTitle(reason)
            .apply {
                if (Build.VERSION.SDK_INT >= 30) {
                    setAllowedAuthenticators(BIOMETRIC_WEAK or DEVICE_CREDENTIAL)
                } else {
                    @Suppress("DEPRECATION")
                    setDeviceCredentialAllowed(true)
                }
            }
            .build()
        val asked = CancellationSignal()
        signal = asked
        prompt.authenticate(
            asked,
            activity.mainExecutor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(
                    result: BiometricPrompt.AuthenticationResult,
                ) {
                    signal = null
                    passed()
                }

                override fun onAuthenticationError(code: Int, message: CharSequence) {
                    // Only this one means what NO_LOCK says; a busy sensor
                    // or a lockout is neither, and the system dialog has
                    // already told the user about those in its own words.
                    signal = null
                    if (code == BiometricPrompt.BIOMETRIC_ERROR_NO_DEVICE_CREDENTIAL) {
                        failed(NO_LOCK)
                    } else {
                        Log.w(TAG, "unlock error $code: $message")
                    }
                }
            },
        )
    }
}
