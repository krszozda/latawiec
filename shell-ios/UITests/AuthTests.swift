import XCTest

/// Drives the sign-in flow against a live server: run
/// `uv run uvicorn examples.auth:app --port 8002` in sdk-python/ first
/// (next to the hello and tabs fixture servers).
final class AuthTests: XCTestCase {
    private func signIn() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8002"
        app.launchEnvironment["LATAWIEC_RESET_AUTH"] = "1"
        app.launch()

        // The guarded home closes with 4401 and the shell falls back to the
        // manifest's login screen.
        XCTAssertTrue(app.staticTexts["Sign in"].waitForExistence(timeout: 10))

        let input = app.descendants(matching: .any)["Access code"].firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        // Let the keyboard's slide-in settle, or taps land on neighbors. The
        // field is a password input, so autocorrect cannot rewrite the code.
        Thread.sleep(forTimeInterval: 1)
        for key in ["s", "e", "z", "a", "m"] {
            app.keys[key].tap()
        }
        app.staticTexts["Enter"].tap()

        XCTAssertTrue(app.staticTexts["Signed in"].waitForExistence(timeout: 10))
        return app
    }

    func testUnauthenticatedShellLandsOnLoginAndSignsIn() {
        let app = signIn()

        // The token persisted in the Keychain: a fresh launch (no reset)
        // renders the guarded screen without passing through login.
        app.terminate()
        let relaunched = XCUIApplication()
        relaunched.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8002"
        relaunched.launch()
        XCTAssertTrue(relaunched.staticTexts["Signed in"].waitForExistence(timeout: 10))
    }

    func testSignOutStartsOverAndForgetsTheToken() {
        let app = signIn()

        app.staticTexts["Sign out"].tap()
        XCTAssertTrue(app.staticTexts["Sign in"].waitForExistence(timeout: 10))

        // Gone for good: a fresh launch (no reset) lands on login, not the
        // guarded home.
        app.terminate()
        let relaunched = XCUIApplication()
        relaunched.launchEnvironment["LATAWIEC_SERVER_URL"] = "http://127.0.0.1:8002"
        relaunched.launch()
        XCTAssertTrue(relaunched.staticTexts["Sign in"].waitForExistence(timeout: 10))
    }
}
