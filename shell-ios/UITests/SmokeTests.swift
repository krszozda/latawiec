import XCTest

/// Walks the example app end-to-end against a live server: run
/// `uv run uvicorn examples.hello:app` in sdk-python/ first.
final class SmokeTests: XCTestCase {
    func testNavigationStateAndFormRoundTrip() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.staticTexts["Hello from Python"].waitForExistence(timeout: 10))

        app.staticTexts["Greeter"].tap()
        // DivKit hides the inner text view from the accessibility tree, so the
        // input is found by its accessibility description and typed into with
        // an on-screen keyboard key (typeText needs a focused tree element).
        let input = app.descendants(matching: .any)["Your name"].firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        input.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        // Let the keyboard's slide-in settle, or the tap lands on a neighbor.
        Thread.sleep(forTimeInterval: 1)
        app.keys["Q"].tap()

        // The text reacts to typing on the device.
        let greeting = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH 'Hello, ' AND label != 'Hello, !'")
        ).firstMatch
        XCTAssertTrue(greeting.waitForExistence(timeout: 5))

        // Autocorrect may rewrite the text as focus leaves, so the submitted
        // value is read back from the thanks screen, not assumed.
        app.staticTexts["Greet"].tap()
        let received = app.staticTexts.matching(
            NSPredicate(format: "label BEGINSWITH 'The server greeted ' AND label != 'The server greeted .'")
        ).firstMatch
        XCTAssertTrue(received.waitForExistence(timeout: 10))
        let name = String(
            received.label.dropFirst("The server greeted ".count).dropLast(1)
        )

        // Back returns to the greeter, whose variable still holds what the
        // server was sent.
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Hello, \(name)!"].waitForExistence(timeout: 5))
    }
}
