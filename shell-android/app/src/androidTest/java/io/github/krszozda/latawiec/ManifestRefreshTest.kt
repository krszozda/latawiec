package io.github.krszozda.latawiec

import android.content.Intent
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
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L
private const val SERVER = "http://10.0.2.2:8005"

// The fixture: `uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005`
// from sdk-python/ on the host. Its tabs mutate through the grow, insert,
// drop and reset actions, which these tests drive directly over HTTP.
@RunWith(AndroidJUnit4::class)
class ManifestRefreshTest {

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

    private fun post(action: String) {
        http.newCall(
            Request.Builder()
                .url("$SERVER/actions/$action")
                .post("{}".toRequestBody("application/json".toMediaType()))
                .build(),
        ).execute().use { assertTrue("$action failed: HTTP ${it.code}", it.isSuccessful) }
    }

    // The tabs are the fixture's own state, and the suites that share this
    // server reach feed and clock as plain screens, which a bar rooting
    // them turns into something else.
    @After
    fun restoreTheBar() {
        post("reset")
    }

    private fun launch() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
    }

    @Test
    fun aTabAddedServerSideAppearsMidSession() {
        post("reset")
        launch()
        awaitScreenText("Live counter")
        assertFalse(device.hasObject(By.text("Clock")))

        post("grow")
        // Any screen fetch carries the new fingerprint; navigating triggers
        // one and the shell refetches the manifest mid-session.
        device.findObject(By.text(screenText("Open clock"))).click()
        awaitScreenText("Clock")
    }

    /** The bar carries each tab's title as its description; the label text
     *  inside the item is not the thing to tap or to ask about selection. */
    private fun tab(title: String) = device.findObject(By.desc(title))

    /** Drives the fixture to two tabs and lands the user on the second. */
    private fun onTheClockTab() {
        post("grow")
        launch()
        awaitScreenText("Live counter")
        tab("Clock").click()
        awaitScreenText("Polled clock")
    }

    @Test
    fun aTabThatMovedKeepsTheUserOnIt() {
        onTheClockTab()

        // The clock polls every second, so the next tick carries the new
        // fingerprint and the shell refetches: three tabs now, with the
        // clock last instead of second.
        post("insert")
        assertTrue(
            "the Feed tab did not appear",
            device.wait(Until.hasObject(By.desc("Feed")), TIMEOUT_MS),
        )
        // The user asked for the clock and is still on it, bar and all.
        awaitScreenText("Polled clock")
        assertTrue("the clock tab lost the highlight", tab("Clock").isSelected)
    }

    @Test
    fun aTabThatIsGoneLandsTheUserOnTheFirstOne() {
        onTheClockTab()

        // Feed takes the clock's place in the bar, so a shell that keeps
        // the user's position rather than their tab lands them there.
        post("drop")
        awaitScreenText("Live counter")
        assertTrue("the home tab did not take the highlight", tab("Home").isSelected)
    }
}
