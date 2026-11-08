package io.github.krszozda.latawiec

import android.content.Intent
import android.net.Uri
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
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L
private const val SERVER = "http://10.0.2.2:8005"

// The fixture: `uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class PullAndPageTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val http = OkHttpClient()

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    private fun open(screen: String) {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("latawiec://$screen"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
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
    fun pullingDownRefetchesTheScreen() {
        open("pull")
        val counter = device.wait(
            Until.findObject(By.text(Pattern.compile("Pulled\\s+\\d+"))),
            TIMEOUT_MS,
        )
        assertNotNull("the pull screen never rendered", counter)
        // swr shows the stale cached render first; wait until the counter
        // stops moving so the baseline is the fresh value, not the cache.
        var count = -1
        repeat(10) {
            val now = device.findObject(By.text(Pattern.compile("Pulled\\s+\\d+")))
                ?.text?.let { Regex("\\d+").find(it)?.value?.toInt() } ?: -1
            if (now == count) return@repeat
            count = now
            android.os.SystemClock.sleep(1_500)
        }

        // The drag starts above the list's top, so the gesture is a pull.
        device.swipe(540, 500, 540, 1700, 40)
        awaitScreenText("Pulled ${count + 1}")
    }

    @Test
    fun loadMoreExtendsTheFeedOnScroll() {
        post("reset_feed")
        open("feed")
        awaitScreenText("Item 10")

        // Scrolling to the sentinel fires its visibility action; the live
        // refresh then delivers the longer list.
        scrollUntil("Item 20")
        // Page three proves the sentinel re-fires (log_limit=0): Android
        // never resets visibility counters across refreshes.
        scrollUntil("Item 30")
    }

    private fun scrollUntil(text: String) {
        repeat(6) {
            device.swipe(540, 1700, 540, 500, 120)
            if (device.wait(Until.hasObject(By.text(screenText(text))), 3_000L)) return
        }
        assertTrue("\"$text\" never appeared while scrolling", false)
    }
}
