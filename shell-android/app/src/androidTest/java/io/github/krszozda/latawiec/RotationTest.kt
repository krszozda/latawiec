package io.github.krszozda.latawiec

import android.content.Intent
import android.net.Uri
import android.os.ParcelFileDescriptor
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.After
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L
private const val SERVER = "http://10.0.2.2:8001"

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class RotationTest {

    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val device = UiDevice.getInstance(instrumentation)
    private val context = instrumentation.targetContext

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    @After
    fun standUpstraight() {
        device.setOrientationNatural()
        device.unfreezeRotation()
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

    private fun shell(command: String): String {
        val output = instrumentation.uiAutomation.executeShellCommand(command)
        return ParcelFileDescriptor.AutoCloseInputStream(output).bufferedReader().use {
            it.readText()
        }
    }

    /**
     * A night-mode switch recreates every activity on the device, and the
     * system is busy for a while afterwards — long enough that the next
     * test's activity would fail to come up. Wait for it to settle.
     */
    private fun setNightMode(on: Boolean) {
        shell("cmd uimode night ${if (on) "yes" else "no"}")
        val wanted = if (on) "yes" else "no"
        val deadline = System.currentTimeMillis() + TIMEOUT_MS
        while (System.currentTimeMillis() < deadline) {
            if (shell("cmd uimode night").contains(wanted)) break
            device.waitForIdle(500)
        }
        device.waitForIdle(2_000)
    }

    @Test
    fun turningThePhoneKeepsWhatTheUserTyped() {
        open("form")
        awaitScreenText("Form tab")
        val input = device.wait(Until.findObject(By.clazz("android.widget.EditText")), TIMEOUT_MS)
        assertNotNull("the form never appeared", input)
        input.text = "Krystian"

        device.setOrientationLeft()
        device.waitForIdle()

        // This is what not being recreated buys: a rebuilt activity would
        // refetch the screen and the typed text would be gone.
        assertTrue(
            "the typed text did not survive the rotation",
            device.wait(Until.hasObject(By.text("Krystian")), TIMEOUT_MS),
        )
    }

    @Test
    fun beingRebuiltPutsTheUserBackWhereTheyWere() {
        // A night-mode switch is not in configChanges, so it rebuilds the
        // activity the same way reclaiming the process does — which is the
        // path that restores the saved stack.
        setNightMode(false)
        open("shop")
        awaitScreenText("Shop tab")

        setNightMode(true)

        awaitScreenText("Shop tab")
        // The root the manifest shows first must be replaced, not stacked
        // under the restored screen: one back press leaves the app.
        device.pressBack()
        assertTrue(
            "a second copy of the tab root was stacked underneath",
            device.wait(Until.gone(By.text(screenText("Shop tab"))), TIMEOUT_MS),
        )
    }

    @org.junit.After
    fun lightMode() {
        setNightMode(false)
    }
}
