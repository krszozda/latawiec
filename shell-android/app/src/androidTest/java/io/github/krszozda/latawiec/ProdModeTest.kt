package io.github.krszozda.latawiec

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L

// The fixture: `uv run uvicorn examples.prod:app --host 0.0.0.0 --port 8004`
// from sdk-python/ on the host — a dev=False server, so screens arrive over
// GET and land in the disk cache instead of the live-reload socket.
@RunWith(AndroidJUnit4::class)
class ProdModeTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

    private fun launch() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8004"),
        )
    }

    // DivKit reports laid-out text with soft line breaks; see TabBarTest.
    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    @Test
    fun screensArriveOverGetAndRevisitsRunTheCache() {
        launch()
        awaitScreenText("Prod home")

        device.findObject(By.text(screenText("About"))).click()
        awaitScreenText("About, cached as static")

        device.pressBack()
        awaitScreenText("Prod home")

        // The second visit takes the static cache hit, which skips the fetch.
        device.findObject(By.text(screenText("About"))).click()
        awaitScreenText("About, cached as static")
    }
}
