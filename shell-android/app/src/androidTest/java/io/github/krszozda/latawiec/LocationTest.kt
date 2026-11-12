package io.github.krszozda.latawiec

import android.annotation.SuppressLint
import android.content.Intent
import android.location.Location
import android.location.LocationManager
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import androidx.core.net.toUri
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
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L

/** Room for the tap to reach the shell on a loaded emulator. */
private const val REGISTER_MS = 2_000L
private const val SERVER = "http://10.0.2.2:8001"
private const val LATITUDE = 52.2297
private const val LONGITUDE = 21.0122

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class LocationTest {

    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val device = UiDevice.getInstance(instrumentation)
    private val context = instrumentation.targetContext
    private val http = OkHttpClient()
    private val manager = context.getSystemService(LocationManager::class.java)!!

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    /** Reading to EOF is what waits for the command to finish. */
    private fun shell(command: String): String {
        val output = instrumentation.uiAutomation.executeShellCommand(command)
        return ParcelFileDescriptor.AutoCloseInputStream(output).bufferedReader().use {
            it.readText()
        }
    }

    /**
     * The prompt is the system's, not the shell's: grant it up front so the
     * test exercises what happens once the answer is yes. A mock provider
     * additionally needs the app-ops bit, and an instrumented test runs
     * under the target app's identity, so both go to its package.
     */
    private fun allowLocation() {
        for (permission in listOf("ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION")) {
            shell("pm grant ${context.packageName} android.permission.$permission")
        }
        shell("appops set ${context.packageName} android:mock_location allow")
        val op = shell("appops get ${context.packageName} android:mock_location")
        assertTrue("mock location not allowed: $op", op.contains("allow"))
    }

    private fun post(action: String) {
        http.newCall(
            Request.Builder()
                .url("$SERVER/actions/$action")
                .post("{}".toRequestBody("application/json".toMediaType()))
                .header("X-Latawiec-Platform", "android")
                .build(),
        ).execute().use { assertTrue(it.isSuccessful) }
    }

    private fun publish(latitude: Double, longitude: Double) {
        manager.setTestProviderLocation(
            LocationManager.GPS_PROVIDER,
            Location(LocationManager.GPS_PROVIDER).apply {
                this.latitude = latitude
                this.longitude = longitude
                accuracy = 5f
                time = System.currentTimeMillis()
                elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
            },
        )
    }

    /**
     * A test provider's fix reaches only listeners already registered, and
     * click() returns before the app has dispatched the tap, so publishing
     * once can land too early and nothing arrives at all. Republishing is
     * free: the shell answers its first fix and unregisters, so the rest
     * reach nobody. Which fix of the few it answers is not asserted here,
     * and the shell does not promise one either.
     */
    private fun publishWhileTheTapLands() {
        val deadline = SystemClock.uptimeMillis() + REGISTER_MS
        while (SystemClock.uptimeMillis() < deadline) {
            publish(LATITUDE, LONGITUDE)
            SystemClock.sleep(250)
        }
    }

    @After
    fun removeTestProvider() {
        runCatching { manager.removeTestProvider(LocationManager.GPS_PROVIDER) }
    }

    // The two 1s are POWER_USAGE_LOW and ACCURACY_FINE. Their named
    // constants live in ProviderProperties, which is API 31, and the shell
    // supports 26.
    @SuppressLint("WrongConstant")
    @Test
    fun aFixLandsInTheScreenVariableAndReachesTheServer() {
        allowLocation()
        post("forget_spot")
        manager.addTestProvider(
            LocationManager.GPS_PROVIDER,
            false, false, false, false, true, true, true, 1, 1,
        )
        manager.setTestProviderEnabled(LocationManager.GPS_PROVIDER, true)

        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData("latawiec://where".toUri())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", SERVER),
        )
        awaitScreenText("Where am I")
        awaitScreenText("Server saw nothing")

        device.findObject(By.text(screenText("Find me"))).click()
        publishWhileTheTapLands()

        // The fix reaches the screen variable...
        awaitScreenText("At 52.229700,21.012200")
        // ...and the follow-up action carries it to the server, which
        // re-renders the live screen with what it received.
        awaitScreenText("Server saw 52.229700,21.012200")
    }
}
