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
// from sdk-python/ on the host; its "boom" action always answers HTTP 500.
@RunWith(AndroidJUnit4::class)
class FeedbackTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

    private fun launch(serverUrl: String) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", serverUrl),
        )
    }

    // DivKit reports laid-out text with soft line breaks; see TabBarTest.
    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    @Test
    fun blankBootShowsTheSpinnerInsteadOfNothing() {
        // Nothing listens on this port; the shell must keep the spinner up
        // rather than crash or sit on an empty window.
        launch("http://10.0.2.2:8009")
        assertTrue(
            "spinner did not appear",
            device.wait(Until.hasObject(By.clazz("android.widget.ProgressBar")), TIMEOUT_MS),
        )
    }

    @Test
    fun failedActionTellsTheUser() {
        launch("http://10.0.2.2:8004")
        assertTrue(
            device.wait(Until.hasObject(By.text(screenText("Prod home"))), TIMEOUT_MS),
        )

        device.findObject(By.text(screenText("Break"))).click()

        assertTrue(
            "error snackbar did not appear",
            device.wait(
                Until.hasObject(By.text(screenText("Something went wrong — try again"))),
                TIMEOUT_MS,
            ),
        )
    }
}
