import XCTest
@testable import LatawiecShell

final class ScreenCacheTests: XCTestCase {
    private let cache = ScreenCache()

    func testRoundTripsAndWipesOnVersionChange() {
        cache.adoptVersion("a")
        cache.store("product/42", policy: "swr", payload: Data(#"{"card": {}}"#.utf8))

        let entry = cache.load("product/42")
        XCTAssertEqual(entry?.policy, "swr")
        XCTAssertEqual(entry?.payload, Data(#"{"card": {}}"#.utf8))

        cache.adoptVersion("b")
        XCTAssertNil(cache.load("product/42"))
    }

    func testCorruptEntryIsDroppedInsteadOfServed() {
        cache.adoptVersion("c")
        // A truncated write: valid policy line, garbage payload.
        cache.store("home", policy: "swr", payload: Data(#"{"truncated": "#.utf8))

        XCTAssertNil(cache.load("home"))
        // The bad file is gone, not retried forever.
        XCTAssertNil(cache.load("home"))
    }
}
