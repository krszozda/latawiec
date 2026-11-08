package io.github.krszozda.latawiec

import android.content.Context
import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.util.regex.Pattern
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L

// The fixture: `uv run uvicorn examples.auth:app --host 0.0.0.0 --port 8002`
// from sdk-python/ on the host. Its home screen is guarded; "sezam" signs in.
@RunWith(AndroidJUnit4::class)
class AuthTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    private val context: Context =
        InstrumentationRegistry.getInstrumentation().targetContext

    @Before
    fun clearToken() {
        TokenStore(context).clear()
    }

    private fun launch() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8002"),
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

    private fun signIn() {
        // The guarded home closes with 4401 and the shell falls back to the
        // manifest's login screen.
        awaitScreenText("Sign in")

        // The empty input surfaces its hint as accessibility text on Android.
        device.findObject(By.text(screenText("Access code"))).click()
        assertTrue(device.wait(Until.hasObject(By.focused(true)), TIMEOUT_MS))
        device.findObject(By.focused(true)).text = "sezam"
        device.pressBack() // dismiss the keyboard so the button is tappable
        // The dismissal refreshes the accessibility tree; an unwaited find
        // can come back null mid-refresh.
        assertTrue(device.wait(Until.hasObject(By.text(screenText("Enter"))), TIMEOUT_MS))
        device.findObject(By.text(screenText("Enter"))).click()

        awaitScreenText("Signed in")
    }

    @Test
    fun unauthenticatedShellLandsOnLoginAndSignsIn() {
        launch()
        signIn()

        // The token persisted: a relaunch (new Activity; the process
        // survives) decrypts the stored token and renders the guarded
        // screen without passing through login.
        device.pressHome()
        launch()
        awaitScreenText("Signed in")
    }

    @Test
    fun signOutStartsOverAndForgetsTheToken() {
        launch()
        signIn()

        device.findObject(By.text(screenText("Sign out"))).click()
        awaitScreenText("Sign in")

        // Gone for good: a fresh launch lands on login, not the guarded home.
        device.pressHome()
        launch()
        awaitScreenText("Sign in")
    }
}
