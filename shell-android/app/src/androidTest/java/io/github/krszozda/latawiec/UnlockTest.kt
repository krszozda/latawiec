package io.github.krszozda.latawiec

import android.content.Intent
import androidx.core.net.toUri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L
private const val SERVER = "http://10.0.2.2:8001"

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host. The emulator has no screen lock, which is
// the state this asserts; confirming a real fingerprint needs a device.
@RunWith(AndroidJUnit4::class)
class UnlockTest {

    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val device = UiDevice.getInstance(instrumentation)
    private val context = instrumentation.targetContext
    private val http = OkHttpClient()

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    private fun post(action: String) {
        http.newCall(
            Request.Builder()
                .url("$SERVER/actions/$action")
                .post("{}".toRequestBody("application/json".toMediaType()))
                .header("X-Latawiec-Platform", "android")
                .build(),
        ).execute().use { assertTrue(it.isSuccessful) }
    }

    @Test
    fun aDeviceWithoutALockSaysSoAndSubmitsNothing() {
        // A vault left open by an earlier run would pass without the shell.
        post("lock_vault")
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData("latawiec://vault".toUri())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
        awaitScreenText("Vault")

        device.findObject(By.text(screenText("Unlock it"))).click()

        awaitScreenText("This device has no lock set up")
        // The gate held: the action never reached the server, so the live
        // screen never flips to Open.
        assertFalse(
            "the action was submitted without the device check passing",
            device.wait(Until.hasObject(By.text(screenText("Open"))), 5_000L),
        )
    }
}
