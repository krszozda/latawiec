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

private const val TIMEOUT_MS = 20_000L
private const val SERVER = "http://10.0.2.2:8001"

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host, which also serves the clip.
//
// This passes on a default build and on a -PwithVideo one: which player
// renders the surface is the shell's choice, and the DSL's is the same
// either way.
@RunWith(AndroidJUnit4::class)
class VideoTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    @Test
    fun aVideoScreenGetsAPlayerSurface() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData("latawiec://clip".toUri())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
        assertTrue(
            "the video screen did not appear",
            device.wait(Until.hasObject(By.text(screenText("A short clip"))), TIMEOUT_MS),
        )
        // The shell publishes which player this build carries, so the
        // assertion follows it: a -PwithVideo build that quietly fell back
        // to the platform player has to fail, not pass.
        val host = device.wait(Until.findObject(By.descStartsWith("player:")), TIMEOUT_MS)
        assertNotNull("the shell never said which player it uses", host)
        val surface = if (host.contentDescription == "player:media3") {
            // ExoPlayer renders into a bare SurfaceView inside PlayerView.
            "android.view.SurfaceView"
        } else {
            "android.widget.VideoView"
        }
        assertTrue(
            "no $surface was attached for ${host.contentDescription}",
            device.wait(Until.hasObject(By.clazz(surface)), TIMEOUT_MS),
        )
    }
}
