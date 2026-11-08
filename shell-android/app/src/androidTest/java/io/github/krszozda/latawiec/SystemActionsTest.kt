package io.github.krszozda.latawiec

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.Uri
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class SystemActionsTest {

    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val device = UiDevice.getInstance(instrumentation)
    private val context = instrumentation.targetContext

    // DivKit reports laid-out text with soft line breaks; see TabBarTest.
    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    private fun openSystemScreen() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("latawiec://system"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8001"),
        )
        awaitScreenText("System actions")
    }

    /** True once the foreground app is no longer the shell. */
    private fun awaitLeavingTheApp(): Boolean {
        val deadline = SystemClock.uptimeMillis() + TIMEOUT_MS
        while (SystemClock.uptimeMillis() < deadline) {
            if (device.currentPackageName != context.packageName) return true
            SystemClock.sleep(250)
        }
        return false
    }

    @Test
    fun copyPutsTheTextOnTheClipboard() {
        openSystemScreen()
        // A stale "kite-42" from an earlier run must not fake the result.
        instrumentation.runOnMainSync {
            context.getSystemService(ClipboardManager::class.java)
                .setPrimaryClip(ClipData.newPlainText("", ""))
        }
        device.findObject(By.text(screenText("Copy code"))).click()

        // Clipboard reads are gated on the focused app; the instrumentation
        // shares the shell's uid, but the write may land a beat after the tap.
        var copied: String? = null
        val deadline = SystemClock.uptimeMillis() + TIMEOUT_MS
        while (copied != "kite-42" && SystemClock.uptimeMillis() < deadline) {
            instrumentation.runOnMainSync {
                val clipboard = context.getSystemService(ClipboardManager::class.java)
                copied = clipboard.primaryClip?.getItemAt(0)?.text?.toString()
            }
            if (copied != "kite-42") SystemClock.sleep(250)
        }
        assertEquals("kite-42", copied)
    }

    @Test
    fun shareOpensTheSystemSheet() {
        openSystemScreen()
        device.findObject(By.text(screenText("Share it"))).click()
        assertTrue("the share sheet did not open", awaitLeavingTheApp())
        device.pressBack()
    }

    @Test
    fun openUrlLeavesTheAppForTheBrowser() {
        openSystemScreen()
        device.findObject(By.text(screenText("Open the site"))).click()
        assertTrue("no external app took over", awaitLeavingTheApp())
        device.pressBack()
    }

    @Test
    fun aTapRunsEveryActionInOrder() {
        openSystemScreen()
        // Buzz is (Haptic, Navigate): the navigation proves the second action
        // ran after the haptic one.
        device.findObject(By.text(screenText("Buzz"))).click()
        awaitScreenText("Details inside the Home tab")
    }
}
