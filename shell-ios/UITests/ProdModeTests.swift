import XCTest

/// Drives the production path against a live server: run
/// `uv run uvicorn examples.prod:app --port 8004` in sdk-python/ first
/// (next to the other fixture servers) — a dev=False server, so screens
/// arrive over GET and land in the disk cache.
final class ProdModeTests: XCTestCase {
    func testScreensArriveOverGetAndRevisitsRunTheCache() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8004"
        app.launch()

        XCTAssertTrue(app.staticTexts["Prod home"].waitForExistence(timeout: 10))

        app.staticTexts["About"].tap()
        XCTAssertTrue(app.staticTexts["About, cached as static"].waitForExistence(timeout: 10))

        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Prod home"].waitForExistence(timeout: 10))

        // The second visit takes the static cache hit, which skips the fetch.
        app.staticTexts["About"].tap()
        XCTAssertTrue(app.staticTexts["About, cached as static"].waitForExistence(timeout: 10))
    }
}
