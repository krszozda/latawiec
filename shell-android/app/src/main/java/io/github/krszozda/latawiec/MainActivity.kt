package io.github.krszozda.latawiec

import android.os.Bundle
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.widget.FrameLayout
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.yandex.div.DivDataTag
import com.yandex.div.core.Div2Context
import com.yandex.div.core.DivConfiguration
import com.yandex.div.core.view2.Div2View
import com.yandex.div.data.DivParsingEnvironment
import com.yandex.div.json.ParsingErrorLogger
import com.yandex.div.picasso.PicassoDivImageLoader
import com.yandex.div2.DivData
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private val http = OkHttpClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val configuration = DivConfiguration.Builder(PicassoDivImageLoader(this)).build()
        val divView = Div2View(Div2Context(this, configuration))
        setContentView(divView, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        lifecycleScope.launch {
            try {
                showScreen(divView, "home")
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "Latawiec: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private suspend fun showScreen(divView: Div2View, name: String) {
        val payload = withContext(Dispatchers.IO) { fetchScreen(name) }
        divView.setData(parseCard(payload), DivDataTag(name))
    }

    private fun fetchScreen(name: String): JSONObject {
        val request = Request.Builder().url("${BuildConfig.SERVER_URL}/screens/$name").build()
        http.newCall(request).execute().use { response ->
            check(response.isSuccessful) { "server returned HTTP ${response.code}" }
            return JSONObject(checkNotNull(response.body).string())
        }
    }

    private fun parseCard(payload: JSONObject): DivData {
        val environment = DivParsingEnvironment(ParsingErrorLogger.LOG)
        payload.optJSONObject("templates")?.let(environment::parseTemplates)
        return DivData(environment, payload.getJSONObject("card"))
    }
}
