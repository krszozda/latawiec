package io.github.krszozda.latawiec

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ScreenCacheTest {

    private val cache =
        ScreenCache(InstrumentationRegistry.getInstrumentation().targetContext)

    @Test
    fun roundTripsAndWipesOnVersionChange() {
        cache.adoptVersion("a")
        cache.store("product/42", "swr", """{"card": {}}""")

        val entry = cache.load("product/42")
        assertEquals("swr", entry?.policy)
        assertEquals("""{"card": {}}""", entry?.payload)

        cache.adoptVersion("b")
        assertNull(cache.load("product/42"))
    }

    @Test
    fun clearDropsEveryEntryAndStoringWorksAgain() {
        cache.adoptVersion("k")
        cache.store("mine", "swr", """{"card": {}}""")

        cache.clear()
        assertNull(cache.load("mine"))

        // Not a version wipe: the next identity's screens store fine.
        cache.store("theirs", "swr", """{"card": {}}""")
        assertEquals("swr", cache.load("theirs")?.policy)
    }

    @Test
    fun aStoreFromBeforeAWipeDoesNotLand() {
        cache.adoptVersion("g")
        val before = cache.generation
        cache.clear()

        // An in-flight response from the signed-out identity arrives late.
        cache.store("inbox", "swr", """{"card": {}}""", asOf = before)
        assertNull(cache.load("inbox"))
    }

    @Test
    fun corruptEntryIsDroppedInsteadOfServed() {
        cache.adoptVersion("c")
        // A truncated write: valid policy line, garbage payload.
        cache.store("home", "swr", """{"truncated": """)

        assertNull(cache.load("home"))
        // The bad file is gone, not retried forever.
        assertNull(cache.load("home"))
    }
}
