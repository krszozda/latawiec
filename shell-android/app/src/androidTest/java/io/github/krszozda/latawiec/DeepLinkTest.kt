package io.github.krszozda.latawiec

import android.content.Intent
import android.net.Uri
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

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class DeepLinkTest {

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

    private fun view(uri: String): Intent =
        Intent(context, MainActivity::class.java)
            .setAction(Intent.ACTION_VIEW)
            .setData(Uri.parse(uri))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    @Test
    fun coldStartDeepLinkPushesScreenOverTheTabRoot() {
        context.startActivity(
            view("latawiec://details")
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8001"),
        )
        awaitScreenText("Details inside the Home tab")

        // The link landed on top of its tab root, not on an empty stack.
        device.pressBack()
        awaitScreenText("Home tab")
    }

    @Test
    fun warmDeepLinkToATabRootSelectsTheTab() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8001"),
        )
        awaitScreenText("Home tab")

        // singleTask routes this to the running activity's onNewIntent.
        context.startActivity(view("latawiec://shop"))
        awaitScreenText("Shop tab")

        // A link to the already-selected tab's root pops back to that root.
        context.startActivity(view("latawiec://home"))
        awaitScreenText("Home tab")
        device.findObject(By.text(screenText("Open details"))).click()
        awaitScreenText("Details inside the Home tab")
        context.startActivity(view("latawiec://home"))
        // The covered root stays in the accessibility tree, so the proof of
        // the pop is the pushed screen going away.
        assertTrue(
            "the deep link did not pop back to the tab root",
            device.wait(
                Until.gone(By.text(screenText("Details inside the Home tab"))),
                TIMEOUT_MS,
            ),
        )
        awaitScreenText("Home tab")
    }
}
