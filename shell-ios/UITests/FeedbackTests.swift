import XCTest

/// Error and loading feedback against the prod fixture: run
/// `uv run uvicorn examples.prod:app --port 8004` in sdk-python/ first;
/// its "boom" action always answers HTTP 500.
final class FeedbackTests: XCTestCase {
    func testBlankBootShowsTheSpinnerInsteadOfNothing() {
        let app = XCUIApplication()
        // Nothing listens on this port; the shell must keep the spinner up
        // rather than crash or sit on an empty window.
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8009"
        app.launch()

        XCTAssertTrue(
            app.activityIndicators.firstMatch.waitForExistence(timeout: 10),
            "spinner did not appear"
        )
    }

    func testFailedActionTellsTheUser() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8004"
        app.launch()

        XCTAssertTrue(app.staticTexts["Prod home"].waitForExistence(timeout: 10))
        app.staticTexts["Break"].tap()

        XCTAssertTrue(
            app.alerts.staticTexts["Something went wrong — try again"]
                .waitForExistence(timeout: 10),
            "error alert did not appear"
        )
    }
}
