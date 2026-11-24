import XCTest

// The fixture: `uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005`
// from sdk-python/ on the host. Its tabs mutate through the grow, insert,
// drop and reset actions, which these tests drive directly over HTTP.
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

    // The tabs are the fixture's own state, and the suites that share this
    // server reach feed and clock as plain screens, which a bar rooting
    // them turns into something else.
    override func tearDown() {
        post("reset")
    }

    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8005"
        app.launch()
        return app
    }

    func testATabAddedServerSideAppearsMidSession() {
        post("reset")
        let app = launch()
        XCTAssertTrue(app.staticTexts["Live counter"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.tabBars.buttons["Clock"].exists)

        post("grow")
        // Any screen fetch carries the new fingerprint; navigating triggers
        // one and the shell refetches the manifest mid-session.
        app.staticTexts["Open clock"].tap()
        XCTAssertTrue(app.tabBars.buttons["Clock"].waitForExistence(timeout: 15))
    }

    /// Drives the fixture to two tabs and lands the user on the second.
    private func onTheClockTab() -> XCUIApplication {
        post("grow")
        let app = launch()
        XCTAssertTrue(app.staticTexts["Live counter"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Clock"].tap()
        XCTAssertTrue(app.staticTexts["Polled clock"].waitForExistence(timeout: 15))
        return app
    }

    func testATabThatMovedKeepsTheUserOnIt() {
        let app = onTheClockTab()

        // The clock polls every second, so the next tick carries the new
        // fingerprint and the shell refetches: three tabs now, with the
        // clock last instead of second.
        post("insert")
        XCTAssertTrue(app.tabBars.buttons["Feed"].waitForExistence(timeout: 15))
        // The user asked for the clock and is still on it, bar and all.
        XCTAssertTrue(app.staticTexts["Polled clock"].exists)
        XCTAssertTrue(app.tabBars.buttons["Clock"].isSelected)
    }

    func testATabThatIsGoneLandsTheUserOnTheFirstOne() {
        let app = onTheClockTab()

        // Feed takes the clock's place in the bar, so a shell that keeps
        // the user's position rather than their tab lands them there.
        post("drop")
        XCTAssertTrue(app.staticTexts["Live counter"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.tabBars.buttons["Home"].isSelected)
    }

    /// Only this shell can get this wrong: it keeps a stack per tab, so the
    /// tab taking over has one of its own to come back to. Android holds a
    /// single stack and roots the first tab outright.
    func testTheTabTakingOverComesBackAtItsRoot() {
        post("grow")
        let app = launch()
        XCTAssertTrue(app.staticTexts["Open clock"].waitForExistence(timeout: 15))
        // Deep in the home tab, then away to another tab.
        app.staticTexts["Open clock"].tap()
        XCTAssertTrue(app.staticTexts["Polled clock"].waitForExistence(timeout: 15))
        app.tabBars.buttons["Clock"].tap()

        post("reset")
        XCTAssertTrue(app.staticTexts["Live counter"].waitForExistence(timeout: 15))
    }
}
