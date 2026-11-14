package io.github.krszozda.latawiec

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What the shell reads out of /manifest. The shells' behaviour around it is
 * covered on a device (TabBarTest, ManifestRefreshTest, ProdModeTest); this
 * pins what the JSON means, which needs no device.
 */
class ManifestParsingTest {

    private fun parse(json: String) = parseManifest(JSONObject(json))

    @Test
    fun tabsKeepTheirServerOrderAndCarryTheirIcons() {
        val manifest = parse(
            """
            {"tabs": [
                {"screen": "home", "title": "Home", "icon": "/icons/home.png"},
                {"screen": "shop", "title": "Shop", "icon": null}
            ]}
            """,
        )
        assertEquals(
            listOf(
                Tab("home", "Home", "/icons/home.png"),
                Tab("shop", "Shop", null),
            ),
            manifest.tabs,
        )
    }

    @Test
    fun aTabMissingItsScreenTakesTheWholeBarDownRatherThanShiftingTheRest() {
        // The bar's items are indexed into the root list, so a half-read
        // array would point tabs at each other's screens.
        val manifest = parse("""{"tabs": [{"title": "Home"}, {"screen": "shop"}]}""")
        assertEquals(emptyList<Tab>(), manifest.tabs)
    }

    @Test
    fun aServerWithoutTabsAsksForNoBar() {
        assertEquals(emptyList<Tab>(), parse("{}").tabs)
        assertEquals(emptyList<Tab>(), parse("""{"tabs": []}""").tabs)
    }

    @Test
    fun devIsTheDefaultSoAPlainServerLiveReloads() {
        assertTrue(parse("{}").dev)
        assertFalse(parse("""{"dev": false}""").dev)
    }

    @Test
    fun loginPushVersionAndAccentReadTheirOwnKeys() {
        val manifest = parse(
            """{"login": "signin", "push": true, "version": "3",
                "theme": {"accent": "#D32F2F"}}""",
        )
        assertEquals("signin", manifest.login)
        assertTrue(manifest.push)
        assertEquals("3", manifest.version)
        assertEquals("#D32F2F", manifest.accent)
    }

    @Test
    fun anAppWithoutThoseKeysGetsNothingInTheirPlace() {
        val manifest = parse("{}")
        assertNull(manifest.login)
        assertFalse(manifest.push)
        assertNull(manifest.version)
        assertEquals("", manifest.accent)
        assertEquals("", manifest.background)
        assertEquals("", manifest.bar)
    }

    @Test
    fun chromeColorsReadTheirOwnKeys() {
        val manifest = parse(
            """{"theme": {"accent": "#6C8CFF", "background": "#07090D", "bar": "#10151C"}}""",
        )
        assertEquals("#07090D", manifest.background)
        assertEquals("#10151C", manifest.bar)
    }

    @Test
    fun theStoredCopyParsesBackToTheSameManifest() {
        // What boots the shell offline is this string, so it has to carry
        // everything the live answer did.
        val served = parse(
            """{"login": "signin", "dev": false, "version": "3",
                "theme": {"accent": "#0A0"},
                "tabs": [{"screen": "home", "title": "Home", "icon": "/i.png"}]}""",
        )
        assertEquals(served, parse(served.raw))
    }
}
