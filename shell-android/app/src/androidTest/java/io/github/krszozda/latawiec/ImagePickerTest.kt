package io.github.krszozda.latawiec

import android.content.ContentValues
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.provider.MediaStore
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

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class ImagePickerTest {

    private val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    private fun screenText(text: String): Pattern = Pattern.compile(text.replace(" ", "\\s+"))

    private fun awaitScreenText(text: String) {
        assertTrue(
            "\"$text\" did not appear",
            device.wait(Until.hasObject(By.text(screenText(text))), TIMEOUT_MS),
        )
    }

    private var seeded: Uri? = null

    @org.junit.After
    fun unseed() {
        seeded?.let { context.contentResolver.delete(it, null, null) }
    }

    /** The picker needs something to show; apps may insert their own media. */
    private fun seedPhoto() {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "latawiec-seed.png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
        }
        val uri = context.contentResolver.insert(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            values,
        ) ?: return
        seeded = uri
        context.contentResolver.openOutputStream(uri)?.use { stream ->
            val bitmap = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(Color.BLUE)
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
        }
    }

    @Test
    fun tappingThePickerOpensTheSystemPhotoPicker() {
        seedPhoto()
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData(Uri.parse("latawiec://photo"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8001"),
        )
        awaitScreenText("Pick a photo")
        device.findObject(By.text(screenText("Choose a photo"))).click()

        // The system picker takes the foreground; its UI varies by OS
        // version, so leaving the shell is the stable signal.
        val deadline = android.os.SystemClock.uptimeMillis() + TIMEOUT_MS
        var left = false
        while (android.os.SystemClock.uptimeMillis() < deadline) {
            if (device.currentPackageName != context.packageName) {
                left = true
                break
            }
            android.os.SystemClock.sleep(250)
        }
        assertTrue("the photo picker never opened", left)
        device.pressBack()
    }
}
