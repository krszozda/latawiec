import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class RotationUITests: XCTestCase {
    override func tearDown() {
        XCUIDevice.shared.orientation = .portrait
        super.tearDown()
    }

    func testTurningTheDeviceKeepsTheScreenTheUserWasOn() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        app.staticTexts["Open details"].tap()
        XCTAssertTrue(
            app.staticTexts["Details inside the Home tab"].waitForExistence(timeout: 15)
        )

        XCUIDevice.shared.orientation = .landscapeLeft

        XCTAssertTrue(
            app.staticTexts["Details inside the Home tab"].waitForExistence(timeout: 15),
            "the pushed screen did not survive the rotation"
        )
        // The bar is laid out by the system, so this is the shell's half:
        // the tabs are still there and still usable on their side.
        XCTAssertTrue(app.tabBars.buttons["Shop"].waitForExistence(timeout: 10))
    }
}
