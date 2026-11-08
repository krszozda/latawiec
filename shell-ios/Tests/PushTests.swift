import XCTest
@testable import LatawiecShell

final class PushTests: XCTestCase {
    func testDeviceTokenBecomesLowercaseHex() {
        XCTAssertEqual(AppDelegate.hex(Data([0x0A, 0xFF, 0x00, 0x42])), "0aff0042")
        XCTAssertEqual(AppDelegate.hex(Data()), "")
    }

    func testPayloadScreenGetsTheDeepLinkPathRules() {
        XCTAssertEqual(AppDelegate.screenPath(raw: "product/42"), "product/42")
        XCTAssertEqual(AppDelegate.screenPath(raw: "/orders/"), "orders")
        XCTAssertNil(AppDelegate.screenPath(raw: ""))
        XCTAssertNil(AppDelegate.screenPath(raw: "a//b"))
        XCTAssertNil(AppDelegate.screenPath(raw: "product/../admin"))
    }
}
