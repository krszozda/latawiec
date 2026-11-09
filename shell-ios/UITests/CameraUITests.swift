import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class CameraUITests: XCTestCase {
    private func openCameraScreen() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://shoot")!)
        XCTAssertTrue(app.staticTexts["Snapshot"].waitForExistence(timeout: 15))
        return app
    }

    /// The simulator has no camera, so this is the path a camera-less
    /// device takes: the shell says so instead of quietly opening the
    /// gallery. Taking an actual shot needs real hardware; which message a
    /// given state earns is pinned in CameraGateTests.
    func testAMissingCameraTellsTheUserInsteadOfOpeningTheGallery() {
        let app = openCameraScreen()

        // The placeholder names the source without being told to.
        app.staticTexts["Take a photo"].tap()

        XCTAssertTrue(
            app.alerts.staticTexts["This device has no camera"].waitForExistence(timeout: 15),
            "the shell did not say the camera was missing"
        )
    }

}
