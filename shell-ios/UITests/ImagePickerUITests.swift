import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host. The simulator ships seeded photos, so the
// full pick → upload → preview loop is drivable end to end.
final class ImagePickerUITests: XCTestCase {
    func testPickingAPhotoUploadsAndPreviews() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://photo")!)
        XCTAssertTrue(app.staticTexts["Pick a photo"].waitForExistence(timeout: 15))

        app.staticTexts["Choose a photo"].tap()
        // PHPicker renders out of process but exposes its grid to the test.
        let photo = app.scrollViews.images.firstMatch
        XCTAssertTrue(photo.waitForExistence(timeout: 15))
        photo.tap()

        // The upload handler echoes a URL carrying the byte count; the
        // screen shows it once the shell sets the variable.
        let echoed = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS 'bytes='")
        ).firstMatch
        XCTAssertTrue(echoed.waitForExistence(timeout: 20))
    }
}
