import XCTest

// The fixture: `uv run uvicorn examples.live:app --host 0.0.0.0 --port 8005`
// from sdk-python/ on the host — production mode, so these tests exercise
// the real GET-then-subscribe (live) and refetch-on-interval (poll) paths.
final class LiveScreenUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8005"
        app.launch()
        XCTAssertTrue(app.staticTexts["Live counter"].waitForExistence(timeout: 15))
        return app
    }

    func testLiveScreenUpdatesInPlaceAfterTheActionRefreshes() {
        let app = launch()
        let counter = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH 'Count: '")
        ).firstMatch
        XCTAssertTrue(counter.waitForExistence(timeout: 15))
        let count = Int(counter.label.dropFirst("Count: ".count))!

        // Bump answers with no navigation; only app.refresh("home") can
        // bring the new value to this screen.
        app.staticTexts["Bump"].tap()
        XCTAssertTrue(app.staticTexts["Count: \(count + 1)"].waitForExistence(timeout: 15))
    }

    func testPolledScreenRefetchesOnItsInterval() {
        let app = launch()
        app.staticTexts["Open clock"].tap()
        XCTAssertTrue(app.staticTexts["Polled clock"].waitForExistence(timeout: 15))

        let tick = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH 'Tick '")
        ).firstMatch
        XCTAssertTrue(tick.waitForExistence(timeout: 15))
        let seen = tick.label
        // refresh=1: within the timeout the second must change.
        let gone = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: app.staticTexts[seen]
        )
        XCTAssertEqual(XCTWaiter().wait(for: [gone], timeout: 15), .completed)
    }
}
