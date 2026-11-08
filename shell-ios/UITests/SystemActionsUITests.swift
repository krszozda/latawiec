import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class SystemActionsUITests: XCTestCase {
    private func openSystemScreen() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://system")!)
        XCTAssertTrue(app.staticTexts["System actions"].waitForExistence(timeout: 15))
        return app
    }

    // CopyToClipboard is DivKit's own typed action (no shell code): the JSON
    // contract is pinned in the Python tests, the Android suite reads the
    // real clipboard, and the simulator pasteboard is too flaky across
    // processes for a stable XCUITest (verified live with simctl pbpaste).

    func testShareOpensTheSystemSheet() {
        let app = openSystemScreen()
        app.staticTexts["Share it"].tap()
        // The activity sheet renders in-process; its private-but-long-stable
        // identifier was verified on the iOS 17 simulator.
        XCTAssertTrue(app.otherElements["ActivityListView"].waitForExistence(timeout: 15))
    }

    func testOpenUrlLeavesTheAppForSafari() {
        let app = openSystemScreen()
        app.staticTexts["Open the site"].tap()
        let safari = XCUIApplication(bundleIdentifier: "com.apple.mobilesafari")
        XCTAssertTrue(safari.wait(for: .runningForeground, timeout: 15))
    }

    func testDeviceContextReachesTheServer() {
        let app = openSystemScreen()
        // The fixture renders ctx.platform/ctx.locale into this line.
        let seen = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH 'Seen from ios'")
        ).firstMatch
        XCTAssertTrue(seen.waitForExistence(timeout: 15))
    }

    func testATapRunsEveryActionInOrder() {
        let app = openSystemScreen()
        // Buzz is (Haptic, Navigate): the navigation proves the second action
        // ran after the haptic one.
        app.staticTexts["Buzz"].tap()
        XCTAssertTrue(
            app.staticTexts["Details inside the Home tab"].waitForExistence(timeout: 15)
        )
    }
}
