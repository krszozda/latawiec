package io.github.krszozda.latawiec

import com.yandex.div.evaluable.Evaluable
import com.yandex.div.evaluable.EvaluationContext
import com.yandex.div.evaluable.Evaluator
import com.yandex.div.evaluable.FunctionProvider
import com.yandex.div.evaluable.StoredValueProvider
import com.yandex.div.evaluable.VariableProvider
import com.yandex.div.evaluable.WarningSender
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The Python DSL sends text the shells have to show as written, and the two
 * characters it cannot send as themselves travel as expressions instead
 * (see `_literal` in sdk-python/src/latawiec/components.py). These are the
 * strings it produces, evaluated by the evaluator DivKit itself ships: what
 * the app's author wrote has to come back out.
 *
 * It lives in this module because this is the only one holding that
 * evaluator, and a DivKit upgrade that changes it fails here — which is
 * the point, since the escaping is only as true as the version it was
 * checked against. The strings are written out rather than derived: a
 * change to `_literal` shows up as a failure in sdk-python's own tests,
 * which pin what it emits, and then this table has to follow.
 */
class LiteralEscapingTest {

    private val evaluator = Evaluator(
        EvaluationContext(
            variableProvider = VariableProvider { null },
            storedValueProvider = StoredValueProvider { null },
            functionProvider = FunctionProvider.STUB,
            warningSender = WarningSender { _, _ -> },
        ),
    )

    private fun shown(sent: String): String = evaluator.eval(Evaluable.prepare(sent))

    @Test
    fun whatTheDslSendsIsWhatTheAuthorWrote() {
        val shownForSent = mapOf(
            "Sent @{'\\@{'}total} items" to "Sent @{total} items",
            "C:@{'\\\\'}users" to "C:\\users",
            "ends with @{'\\\\'}" to "ends with \\",
            "both C:@{'\\\\'}u @{'\\@{'}v}" to "both C:\\u @{v}",
            "@{'\\@{'}a}@{'\\@{'}b}" to "@{a}@{b}",
            "'quoted' @{'\\@{'}a} 100%" to "'quoted' @{a} 100%",
            // A backslash right in front of the marker, which escaping in
            // place cannot survive: the escape itself reaches the screen.
            "a@{'\\\\'}@{'\\@{'}b}" to "a\\@{b}",
        )

        for ((sent, expected) in shownForSent) {
            assertEquals("evaluating [$sent]", expected, shown(sent))
        }
    }
}
