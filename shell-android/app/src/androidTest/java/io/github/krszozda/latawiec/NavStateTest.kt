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

// The fixture: `uv run uvicorn examples.hello:app --host 0.0.0.0` on port
// 8000. The greeter's name variable lives in its screen's DivKit card, so it
// survives back-navigation only if the screen's view survives too.
@RunWith(AndroidJUnit4::class)
class NavStateTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

    // DivKit reports laid-out text with soft line breaks; see TabBarTest.
    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    @Test
    fun typedStateSurvivesBackNavigation() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8000"),
        )
        awaitScreenText("Hello from Python")

        device.findObject(By.text(screenText("Greeter"))).click()
        // The empty input surfaces its hint as accessibility text on Android.
        awaitScreenText("Your name")
        device.findObject(By.text(screenText("Your name"))).click()
        assertTrue(device.wait(Until.hasObject(By.focused(true)), TIMEOUT_MS))
        device.findObject(By.focused(true)).text = "kite"
        device.pressBack() // dismiss the keyboard

        device.findObject(By.text(screenText("Greet"))).click()
        awaitScreenText("The server greeted kite.")

        // Back pops to the greeter view itself: the variable the user typed
        // is still in its card, not refetched away.
        device.pressBack()
        awaitScreenText("Hello, kite!")
    }
}
