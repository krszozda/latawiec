package io.github.krszozda.latawiec

import android.content.Intent
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 20_000L
private const val SERVER = "http://10.0.2.2:8001"

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host. The tiles come from the network, so this
// needs the emulator to have one.
@RunWith(AndroidJUnit4::class)
class MapTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    @Test
    fun theMapDrawsItselfAndCanBePanned() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("latawiec://map"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
        assertTrue(
            "the map screen did not appear",
            device.wait(Until.hasObject(By.text(screenText("Where we fly"))), TIMEOUT_MS),
        )

        val map = device.wait(Until.findObject(By.descStartsWith("map ")), TIMEOUT_MS)
        assertNotNull("the map view was never created", map)
        // The view publishes where it is looking, which is the only thing
        // observable about a canvas full of tiles.
        val before = map.contentDescription

        val bounds = map.visibleBounds
        device.swipe(
            bounds.centerX(), bounds.centerY(), bounds.centerX() - 300, bounds.centerY(), 20,
        )
        device.waitForIdle()

        val after = device.wait(Until.findObject(By.descStartsWith("map ")), TIMEOUT_MS)
        assertNotNull("the map disappeared after a drag", after)
        assertNotEquals("the drag never moved the map", before, after.contentDescription)
    }
}
