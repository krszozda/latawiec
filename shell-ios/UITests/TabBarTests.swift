import XCTest

/// Exercises the manifest-driven tab bar against a live server: run
/// `uv run uvicorn examples.tabs:app --port 8001` in sdk-python/ first
/// (next to the `examples.hello` server the smoke tests use).
final class TabBarTests: XCTestCase {
    func testTabsSwitchPushAndBack() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()

        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 10))
        let bar = app.tabBars.firstMatch
        XCTAssertTrue(bar.exists)
        XCTAssertTrue(bar.buttons["Home"].exists)
        XCTAssertTrue(bar.buttons["Shop"].exists)
        XCTAssertTrue(bar.buttons["Form"].exists)

        bar.buttons["Shop"].tap()
        XCTAssertTrue(app.staticTexts["Shop tab"].waitForExistence(timeout: 10))

        bar.buttons["Home"].tap()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 10))
        app.staticTexts["Open details"].tap()
        XCTAssertTrue(app.staticTexts["Details inside the Home tab"].waitForExistence(timeout: 10))
        // The push landed inside the tab: the bar is still there.
        XCTAssertTrue(bar.exists)

        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 10))
    }
}
