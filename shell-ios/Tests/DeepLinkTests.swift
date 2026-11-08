import XCTest
@testable import LatawiecShell

final class DeepLinkTests: XCTestCase {
    func testCustomSchemeStartsTheScreenAtTheHost() {
        XCTAssertEqual(
            AppDelegate.screenPath(URL(string: "latawiec://product/42")!),
            "product/42"
        )
        XCTAssertEqual(AppDelegate.screenPath(URL(string: "latawiec://shop")!), "shop")
        XCTAssertEqual(AppDelegate.screenPath(URL(string: "latawiec://shop/")!), "shop")
    }

    func testUniversalLinkCarriesTheScreenInThePath() {
        XCTAssertEqual(
            AppDelegate.screenPath(URL(string: "https://kites.example.com/product/42")!),
            "product/42"
        )
        // The https host is the app's domain, never part of the screen.
        XCTAssertNil(AppDelegate.screenPath(URL(string: "https://kites.example.com/")!))
    }

    func testBareOpenNamesNoScreen() {
        XCTAssertNil(AppDelegate.screenPath(URL(string: "latawiec://")!))
    }

    func testPathReshapingSegmentsAreDropped() {
        XCTAssertNil(AppDelegate.screenPath(URL(string: "latawiec://product/../admin")!))
        XCTAssertNil(AppDelegate.screenPath(URL(string: "https://kites.example.com/a//b")!))
        XCTAssertNil(AppDelegate.screenPath(URL(string: "https://kites.example.com/./shop")!))
    }

    func testSchemeComparisonIgnoresCase() {
        XCTAssertEqual(
            AppDelegate.screenPath(URL(string: "HTTPS://kites.example.com/shop")!),
            "shop"
        )
    }
}
