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
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L
private const val SERVER = "http://10.0.2.2:8001"

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class SubmitTypesTest {

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

    /**
     * A Switch holds a boolean and a Slider an integer, and the action URL
     * carries both through DivKit's own evaluator. encodeUri takes a string
     * and matches no other type, so an unconverted value fails the whole
     * URL and the tap is dropped in silence — which is what this catches.
     */
    @Test
    fun aBooleanAndAnIntegerSurviveTheTripToTheServer() {
        // Settings left over from an earlier run would pass without a tap.
        post("forget_settings")
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData("latawiec://settings".toUri())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
        awaitScreenText("Settings")
        awaitScreenText("Server saw nothing")

        device.findObject(By.clazz("android.widget.Switch")).click()
        device.findObject(By.text(screenText("Save"))).click()

        // The slider is left where it started: moving it precisely is beside
        // the point, and its untouched value travels the same way.
        awaitScreenText("Server saw dark=true size=3")
    }
}
