package io.github.krszozda.latawiec

import android.content.Intent
import androidx.core.net.toUri
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
private const val SERVER = "http://10.0.2.2:8001"

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class CameraTest {

    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val device = UiDevice.getInstance(instrumentation)
    private val context = instrumentation.targetContext

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    /** The emulator runs AOSP Camera2, whose buttons these are. */
    private fun cameraButton(id: String) = device.wait(
        Until.findObject(By.res("com.android.camera2:id/$id")),
        TIMEOUT_MS,
    )

    @Test
    fun aShotFromTheCameraReachesTheServerAndPreviews() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData("latawiec://shoot".toUri())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
        assertTrue(
            "the camera screen did not appear",
            device.wait(Until.hasObject(By.text(screenText("Snapshot"))), TIMEOUT_MS),
        )

        // The placeholder the DSL renders is also the tap target.
        device.findObject(By.text(screenText("Take a photo"))).click()

        val shutter = cameraButton("shutter_button")
        assertNotNull("no camera app came forward for the shot", shutter)
        shutter.click()
        val accept = cameraButton("done_button")
        assertNotNull("the camera never offered the shot back", accept)
        accept.click()

        // The fixture echoes the byte count it received, so a URL carrying
        // one proves the shot travelled the FileProvider URI, the upload and
        // @app.upload whole, and landed in the picker's variable.
        assertTrue(
            "the shot never reached the server",
            device.wait(Until.hasObject(By.textContains("bytes=")), TIMEOUT_MS),
        )
    }
}
