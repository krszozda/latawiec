import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host. XCUITest cannot reach simctl, so the
// simulator needs its position and the permission set from outside first:
//
//   xcrun simctl location booted set 52.2297,21.0122
//   xcrun simctl privacy booted grant location io.github.krszozda.latawiec.shell
final class LocationUITests: XCTestCase {
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

    func testAFixLandsInTheScreenVariableAndReachesTheServer() {
        // A fix left over from the last run would let the assertions pass
        // without the shell doing anything.
        post("forget_spot")

        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://where")!)
        XCTAssertTrue(app.staticTexts["Where am I"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["Server saw nothing"].waitForExistence(timeout: 15))

        app.staticTexts["Find me"].tap()

        // The fix reaches the screen variable...
        XCTAssertTrue(
            app.staticTexts["At 52.229700,21.012200"].waitForExistence(timeout: 20)
        )
        // ...and the follow-up action carries it to the server, which
        // re-renders the live screen with what it received.
        XCTAssertTrue(
            app.staticTexts["Server saw 52.229700,21.012200"].waitForExistence(timeout: 20)
        )
    }
}
