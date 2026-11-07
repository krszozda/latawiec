package io.github.krszozda.latawiec

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L

// The fixtures: `uv run uvicorn examples.hello:app --host 0.0.0.0` (port 8000)
// and `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`, both from
// sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class TabBarTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

    private fun launch(serverUrl: String) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", serverUrl),
        )
    }

    // DivKit reports its laid-out text to accessibility, soft line breaks
    // included, so screen texts are matched with \s+ between words. The bar's
    // native item labels match exactly.
    private fun screenText(text: String): Pattern =
        Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    @Test
    fun tabsSwitchPushAndBack() {
        launch("http://10.0.2.2:8001")
        awaitScreenText("Home tab")
        assertTrue(device.hasObject(By.text("Shop")))
        assertTrue(device.hasObject(By.text("Form")))

        device.findObject(By.text("Shop")).click()
        awaitScreenText("Shop tab")

        device.findObject(By.text("Home")).click()
        awaitScreenText("Home tab")
        device.findObject(By.text(screenText("Open details"))).click()
        awaitScreenText("Details inside the Home tab")

        // Back pops the pushed screen to the tab root, not out of the app.
        device.pressBack()
        awaitScreenText("Home tab")
        assertTrue(device.hasObject(By.text("Shop")))
    }

    @Test
    fun serverWithoutTabsShowsNoBar() {
        launch("http://10.0.2.2:8000")
        awaitScreenText("Hello from Python")
        assertFalse(device.hasObject(By.text("Shop")))
        assertFalse(device.hasObject(By.text("Form")))
    }
}
