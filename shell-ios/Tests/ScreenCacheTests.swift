import XCTest
@testable import LatawiecShell

final class ScreenCacheTests: XCTestCase {
    private let cache = ScreenCache()

    func testRoundTripsAndWipesOnVersionChange() {
        cache.adoptVersion("a")
        cache.store("product/42", policy: "swr", payload: Data(#"{"card": {}}"#.utf8), asOf: cache.generation)

        let entry = cache.load("product/42")
        XCTAssertEqual(entry?.policy, "swr")
        XCTAssertEqual(entry?.payload, Data(#"{"card": {}}"#.utf8))

        cache.adoptVersion("b")
        XCTAssertNil(cache.load("product/42"))
    }

    func testClearDropsEveryEntryAndStoringWorksAgain() {
        cache.adoptVersion("k")
        cache.store("mine", policy: "swr", payload: Data(#"{"card": {}}"#.utf8), asOf: cache.generation)

        cache.clear()
        XCTAssertNil(cache.load("mine"))

        // Not a version wipe: the next identity's screens store fine.
        cache.store("theirs", policy: "swr", payload: Data(#"{"card": {}}"#.utf8), asOf: cache.generation)
        XCTAssertEqual(cache.load("theirs")?.policy, "swr")
    }

    func testAStoreFromBeforeAWipeDoesNotLand() {
        cache.adoptVersion("g")
        let before = cache.generation
        cache.clear()

        // An in-flight response from the signed-out identity arrives late.
        cache.store("inbox", policy: "swr", payload: Data(#"{"card": {}}"#.utf8), asOf: before)
        XCTAssertNil(cache.load("inbox"))
    }

    func testCorruptEntryIsDroppedInsteadOfServed() {
        cache.adoptVersion("c")
        // A truncated write: valid policy line, garbage payload.
        cache.store("home", policy: "swr", payload: Data(#"{"truncated": "#.utf8), asOf: cache.generation)

        XCTAssertNil(cache.load("home"))
        // The bad file is gone, not retried forever.
        XCTAssertNil(cache.load("home"))
    }
}
