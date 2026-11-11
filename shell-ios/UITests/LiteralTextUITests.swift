import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class LiteralTextUITests: XCTestCase {
    /// DivKit evaluates the strings it is given, so text an app did not
    /// write as an expression has to arrive escaped — and the two platforms
    /// disagree about when a string is parsed at all, which is the half of
    /// this that only a device can answer.
    func testTextArrivesAsWrittenUnlessItAskedToBeEvaluated() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://literal")!)

        XCTAssertTrue(
            app.staticTexts["Sent @{total} items"].waitForExistence(timeout: 15),
            "an expression someone typed was evaluated instead of shown"
        )
        XCTAssertTrue(
            app.staticTexts["Saved to C:\\reports"].waitForExistence(timeout: 15),
            "the escaped backslash reached the screen doubled, or not at all"
        )
        XCTAssertTrue(
            app.staticTexts["Ends with a backslash \\\\"].waitForExistence(timeout: 15),
            "a trailing backslash swallowed what the DSL put after it"
        )
        XCTAssertTrue(
            app.staticTexts["Adds up to 2"].waitForExistence(timeout: 15),
            "an Expression stopped being evaluated"
        )
    }
}
