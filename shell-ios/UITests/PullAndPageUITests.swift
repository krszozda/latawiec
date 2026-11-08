import XCTest

// The fixture: `uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005`
// from sdk-python/ on the host.
final class PullAndPageUITests: XCTestCase {
    private let server = URL(string: "http://127.0.0.1:8005")!

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

    private func launch(into screen: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8005"
        app.launch()
        XCTAssertTrue(app.staticTexts["Live counter"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://\(screen)")!)
        return app
    }

    func testPullingDownRefetchesTheScreen() {
        let app = launch(into: "pull")
        let counter = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH 'Pulled '")
        ).firstMatch
        XCTAssertTrue(counter.waitForExistence(timeout: 15))
        // swr shows the stale cached render first; wait until the counter
        // stops moving so the baseline is the fresh value, not the cache.
        var count = -1
        for _ in 0..<10 {
            let now = Int(counter.label.dropFirst("Pulled ".count)) ?? -1
            if now == count { break }
            count = now
            Thread.sleep(forTimeInterval: 1.5)
        }

        pull(app, until: count + 1)
        // The control survives the re-render; a second pull works too.
        pull(app, until: count + 2)
    }

    /// UIRefreshControl wants a slow deliberate drag, and a gesture can
    /// miss its registration window on a busy simulator — retry once.
    private func pull(_ app: XCUIApplication, until expected: Int) {
        for _ in 0..<3 {
            let anchor = app.staticTexts.matching(
                NSPredicate(format: "label BEGINSWITH 'Pulled '")
            ).firstMatch
            let start = anchor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            let end = start.withOffset(CGVector(dx: 0, dy: 500))
            start.press(
                forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2
            )
            if app.staticTexts["Pulled \(expected)"].waitForExistence(timeout: 8) { return }
        }
        XCTFail("the pull never refetched up to Pulled \(expected)")
    }

    func testLoadMoreExtendsTheFeedOnScroll() {
        post("reset_feed")
        let app = launch(into: "feed")
        XCTAssertTrue(app.staticTexts["Item 10"].waitForExistence(timeout: 15))

        scroll(app, until: "Item 20")
        // Page three proves the sentinel re-fires across refreshes.
        scroll(app, until: "Item 30")
    }

    private func scroll(_ app: XCUIApplication, until text: String) {
        for _ in 0..<6 {
            app.swipeUp()
            if app.staticTexts[text].waitForExistence(timeout: 3) { return }
        }
        XCTFail("\(text) never appeared while scrolling")
    }
}
