import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class SubmitTypesUITests: XCTestCase {
    private let server = URL(string: "http://127.0.0.1:8001")!

    private func post(_ action: String) {
        var request = URLRequest(url: server.appendingPathComponent("actions/\(action)"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("ios", forHTTPHeaderField: "X-Latawiec-Platform")
        request.httpBody = Data("{}".utf8)
        let done = expectation(description: action)
        URLSession.shared.dataTask(with: request) { _, response, _ in
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 10)
    }

    /// The Android half of this is SubmitTypesTest; both platforms evaluate
    /// the action URL themselves, so each needs its own run to show that a
    /// value which is not a string still reaches the server.
    func testABooleanAndAnIntegerSurviveTheTripToTheServer() {
        // Settings left over from an earlier run would pass without a tap.
        post("forget_settings")

        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://settings")!)
        XCTAssertTrue(app.staticTexts["Settings"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["Server saw nothing"].waitForExistence(timeout: 15))

        app.switches.firstMatch.tap()
        app.staticTexts["Save"].tap()

        // The slider is left where it started: moving it precisely is beside
        // the point, and its untouched value travels the same way.
        XCTAssertTrue(
            app.staticTexts["Server saw dark=true size=3"].waitForExistence(timeout: 15)
        )
    }
}
