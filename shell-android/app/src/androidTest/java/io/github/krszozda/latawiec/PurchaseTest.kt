package io.github.krszozda.latawiec

import android.content.Intent
import android.net.Uri
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
// from sdk-python/ on the host.
//
// Buying for real needs a product in Play Console and a licence-tested
// account, so what both builds can be held to is this: the tap says
// something, and grants nothing. A default build says payments are not in
// it. A -PwithBilling build says whichever is true of the device: this
// emulator ships Play Store without the billing API, so it reports the
// store as unreachable; a phone missing only the product names it.
@RunWith(AndroidJUnit4::class)
class PurchaseTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    @Test
    fun aTapAlwaysSaysSomething() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("latawiec://shop_kite"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
        assertTrue(
            "the shop screen did not appear",
            device.wait(Until.hasObject(By.text(screenText("Kite shop"))), TIMEOUT_MS),
        )

        val host = device.wait(Until.findObject(By.descStartsWith("player:")), TIMEOUT_MS)
        assertNotNull("the shell never said which build this is", host)
        val built = host.contentDescription.contains("store:play")

        device.findObject(By.text(screenText("Buy a kite"))).click()

        val expected = if (built) {
            listOf("The store could not be reached", "The store has no product called kite.one")
        } else {
            listOf("This app was not built to take payments")
        }
        val said = expected.any { message ->
            device.wait(Until.hasObject(By.textContains(message)), TIMEOUT_MS / expected.size)
        }
        assertTrue("the tap said nothing; expected one of $expected", said)
        // Nothing was granted on the way.
        assertTrue(
            "something was granted without a purchase",
            device.hasObject(By.text(screenText("Nothing bought"))),
        )
    }
}
