import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class DeepLinkUITests: XCTestCase {
    func testDeepLinksPushAScreenAndSelectATab() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))

        XCUIDevice.shared.system.open(URL(string: "latawiec://details")!)
        XCTAssertTrue(
            app.staticTexts["Details inside the Home tab"].waitForExistence(timeout: 15)
        )

        // A link to the already-selected tab's root pops back to that root;
        // the proof of the pop is the pushed screen going away.
        XCUIDevice.shared.system.open(URL(string: "latawiec://home")!)
        let detailsGone = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: app.staticTexts["Details inside the Home tab"]
        )
        XCTAssertEqual(XCTWaiter().wait(for: [detailsGone], timeout: 15), .completed)
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))

        XCUIDevice.shared.system.open(URL(string: "latawiec://shop")!)
        XCTAssertTrue(app.staticTexts["Shop tab"].waitForExistence(timeout: 15))
    }
}
