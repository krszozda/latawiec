import StoreKitTest
import XCTest
@testable import LatawiecShell

/// Buys for real, against the local store in Latawiec.storekit, so the
/// path that matters — a signed receipt coming back — is covered without
/// App Store Connect or a sandbox account.
final class StoreTests: XCTestCase {
    private var session: SKTestSession!

    override func setUpWithError() throws {
        session = try SKTestSession(configurationFileNamed: "Latawiec")
        session.resetToDefaultState()
        session.clearTransactions()
        // The purchase sheet would otherwise wait for a tap.
        session.disableDialogs = true
    }

    override func tearDown() {
        // The session lives on the simulator, not in this process: leaving
        // it open would let other tests buy by accident.
        session.clearTransactions()
        session = nil
        super.tearDown()
    }

    func testBuyingReturnsAReceiptWorthSending() async {
        let outcome = await Store.buy("kite.one")

        guard case let .bought(purchase) = outcome else {
            return XCTFail("expected a purchase, got \(outcome)")
        }
        // A JWS receipt is three dot-separated parts; the server needs all
        // of it to check Apple's signature.
        XCTAssertEqual(purchase.receipt.split(separator: ".").count, 3, "not a signed receipt")
        // The product comes from the transaction, not from the tap.
        XCTAssertEqual(purchase.product, "kite.one")
    }

    func testAPurchaseStaysUnfinishedUntilItIsDelivered() async throws {
        guard case let .bought(purchase) = await Store.buy("kite.one") else {
            return XCTFail("expected a purchase")
        }

        // Still owed to the customer: StoreKit replays it on next launch,
        // which is what makes a failed submit recoverable.
        var unfinished = 0
        for await _ in StoreKit.Transaction.unfinished { unfinished += 1 }
        XCTAssertEqual(unfinished, 1, "the purchase was finished before delivery")

        await purchase.finish()
        var left = 0
        for await _ in StoreKit.Transaction.unfinished { left += 1 }
        XCTAssertEqual(left, 0, "finishing did not settle the purchase")
    }

    func testAStoreThatRefusesSaysSoRatherThanGranting() async {
        session.failTransactionsEnabled = true

        let outcome = await Store.buy("kite.one")

        guard case .failed = outcome else {
            return XCTFail("a refused purchase must not grant: \(outcome)")
        }
    }

    func testAnUnknownProductSaysWhichOne() async {
        let outcome = await Store.buy("kite.nope")

        guard case let .failed(message) = outcome else {
            return XCTFail("expected a failure, got \(outcome)")
        }
        XCTAssertTrue(message.contains("kite.nope"), "the message hides which product: \(message)")
    }
}
