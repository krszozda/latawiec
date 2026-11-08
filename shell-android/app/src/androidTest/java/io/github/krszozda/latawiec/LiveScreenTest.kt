package io.github.krszozda.latawiec

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L

// The fixture: `uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005`
// from sdk-python/ on the host — production mode, so these tests exercise
// the real GET-then-subscribe (live) and refetch-on-interval (poll) paths.
@RunWith(AndroidJUnit4::class)
class LiveScreenTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    // DivKit reports laid-out text with soft line breaks; see TabBarTest.
    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    private fun launch() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8005"),
        )
        awaitScreenText("Live counter")
    }

    @Test
    fun liveScreenUpdatesInPlaceAfterTheActionRefreshes() {
        launch()
        val counter = device.wait(
            Until.findObject(By.text(Pattern.compile("Count:\\s+\\d+"))),
            TIMEOUT_MS,
        )
        assertNotNull("the counter never rendered", counter)
        val count = Regex("\\d+").find(counter.text)!!.value.toInt()

        // Bump answers with no navigation; only app.refresh("home") can
        // bring the new value to this screen.
        device.findObject(By.text(screenText("Bump"))).click()
        awaitScreenText("Count: ${count + 1}")
    }

    @Test
    fun polledScreenRefetchesOnItsInterval() {
        launch()
        device.findObject(By.text(screenText("Open clock"))).click()
        awaitScreenText("Polled clock")

        val tick = device.wait(
            Until.findObject(By.text(Pattern.compile("Tick\\s+.+"))),
            TIMEOUT_MS,
        )
        assertNotNull("the clock never rendered", tick)
        // refresh=1: within the timeout the second must change.
        assertTrue(
            "the polled screen never refetched",
            device.wait(Until.gone(By.text(tick.text)), TIMEOUT_MS),
        )
    }
}
