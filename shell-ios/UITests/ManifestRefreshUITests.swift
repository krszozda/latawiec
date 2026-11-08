import XCTest

// The fixture: `uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005`
// from sdk-python/ on the host. Its tabs mutate through the grow/reset
// actions, which this test drives directly over HTTP.
final class ManifestRefreshUITests: XCTestCase {
    private let server = URL(string: "http://127.0.0.1:8005")!

    private func post(_ action: String) {
        var request = URLRequest(url: server.appendingPathComponent("actions/\(action)"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data("{}".utf8)
        let done = expectation(description: action)
        URLSession.shared.dataTask(with: request) { _, response, _ in
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 10)
    }

    func testATabAddedServerSideAppearsMidSession() {
        post("reset")
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8005"
        app.launch()
        XCTAssertTrue(app.staticTexts["Live counter"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.tabBars.buttons["Clock"].exists)

        post("grow")
        // Any screen fetch carries the new fingerprint; navigating triggers
        // one and the shell refetches the manifest mid-session.
        app.staticTexts["Open clock"].tap()
        XCTAssertTrue(app.tabBars.buttons["Clock"].waitForExistence(timeout: 15))
    }
}
