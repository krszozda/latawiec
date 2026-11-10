import XCTest

// The fixture: `uv run uvicorn examples.tabs:app --host 0.0.0.0 --port 8001`
// from sdk-python/ on the host.
final class UnlockUITests: XCTestCase {
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

    /// The whole point of the gate: the tap raises the device's own check
    /// and submits nothing until it passes. The simulator reports a
    /// passcode it cannot actually be asked for, so the prompt stays up and
    /// unanswered — which is exactly the state worth asserting. Confirming
    /// a real Face ID needs Features ▸ Face ID ▸ Enrolled, or a device.
    func testTheTapAloneSubmitsNothing() {
        // A vault left open by the last run would pass without the shell.
        post("lock_vault")

        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8001"
        app.launch()
        XCTAssertTrue(app.staticTexts["Home tab"].waitForExistence(timeout: 15))
        XCUIDevice.shared.system.open(URL(string: "latawiec://vault")!)
        XCTAssertTrue(app.staticTexts["Vault"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["Locked"].waitForExistence(timeout: 15))

        app.staticTexts["Unlock it"].tap()

        // The system sheet is up: the shell is waiting, not failing. Its
        // own alerts would mean the tap never reached the device check.
        XCTAssertFalse(
            app.alerts.element.waitForExistence(timeout: 5),
            "the shell gave up instead of asking the device"
        )
        // And the live screen would say Open the moment the action landed.
        XCTAssertFalse(
            app.staticTexts["Open"].exists,
            "the action was submitted without the device check passing"
        )
        // Leaving takes the system prompt with it.
        app.terminate()
    }
}
