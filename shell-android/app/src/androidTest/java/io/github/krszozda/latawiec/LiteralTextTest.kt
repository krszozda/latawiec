package io.github.krszozda.latawiec

import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.net.toUri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

private const val TIMEOUT_MS = 15_000L

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
@RunWith(AndroidJUnit4::class)
class LiteralTextTest {

    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext

    // Unlike its siblings this test reads the views instead of asking
    // UiAutomator for text. UiAutomator's search does not reach the
    // "Sent @{total} items" node at all: on the emulator every matcher comes
    // back empty for it — the exact string, a pattern, ".*total.*" with
    // DOTALL, even By.textContains("Sent") — while crawling the accessibility
    // tree directly finds that node holding exactly those 19 characters, and
    // the same matchers do find its three sibling texts. Why is unexplained.
    // The views are what the user sees, so the views are what this asserts.
    private fun views(): List<View> {
        val views = mutableListOf<View>()
        instrumentation.runOnMainSync {
            ActivityLifecycleMonitorRegistry.getInstance()
                .getActivitiesInStage(Stage.RESUMED)
                .forEach { collect(it.window.decorView, views) }
        }
        return views
    }

    private fun collect(view: View, into: MutableList<View>) {
        into.add(view)
        if (view is ViewGroup) {
            for (i in 0 until view.childCount) collect(view.getChildAt(i), into)
        }
    }

    private fun texts(views: List<View>): List<String> =
        views.filterIsInstance<TextView>().map { it.text.toString() }

    private fun screens(views: List<View>): List<String> =
        views.filterIsInstance<ScreenView>().map { it.name }

    /**
     * DivKit evaluates the strings it is handed, so text an app did not write
     * as an expression has to arrive escaped. Android is the half of that only
     * a device answers: its evaluator runs on a string the moment it holds
     * "@{" anywhere, and an escape it cannot read renders the text as nothing.
     */
    @Test
    fun textArrivesAsWrittenUnlessItAskedToBeEvaluated() {
        context.startActivity(
            Intent(context, MainActivity::class.java)
                .setAction(Intent.ACTION_VIEW)
                .setData("latawiec://literal".toUri())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                .putExtra("serverUrl", "http://10.0.2.2:8001"),
        )
        // The screen's four texts bind in one pass, so the last one is the cue.
        val deadline = SystemClock.uptimeMillis() + TIMEOUT_MS
        var views = views()
        while (SystemClock.uptimeMillis() < deadline && "Adds up to 2" !in texts(views)) {
            SystemClock.sleep(250L)
            views = views()
        }
        // Told apart from an escaping failure: the deep link may never have
        // landed, or the fixture may not be up at all.
        assertTrue(
            "the literal screen never arrived, screens=${screens(views)}",
            "literal" in screens(views),
        )

        val shown = texts(views)
        assertTrue(
            "an expression someone typed was evaluated instead of shown: $shown",
            "Sent @{total} items" in shown,
        )
        assertTrue(
            "the escaped backslash reached the screen doubled, or not at all: $shown",
            "Saved to C:\\reports" in shown,
        )
        assertTrue(
            "a trailing backslash swallowed what the DSL put after it: $shown",
            "Ends with a backslash \\\\" in shown,
        )
        assertTrue("an Expression stopped being evaluated: $shown", "Adds up to 2" in shown)
    }
}
