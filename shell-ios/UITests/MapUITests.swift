import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class MapUITests: XCTestCase {
    func testTheMapRendersAsANativeMapView() {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://map")!)
        XCTAssertTrue(app.staticTexts["Where we fly"].waitForExistence(timeout: 15))

        // A real MKMapView, not a placeholder: XCUITest only reports this
        // element type for the genuine article.
        XCTAssertTrue(app.maps.firstMatch.waitForExistence(timeout: 15), "no map view rendered")
        // MapKit publishes each annotation, so the pins arrived too.
        XCTAssertTrue(
            app.maps.firstMatch.otherElements["Warszawa"].waitForExistence(timeout: 15),
            "the marker never reached the map"
        )
    }
}
