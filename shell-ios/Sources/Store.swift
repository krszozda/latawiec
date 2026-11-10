import StoreKit
import os

private let log = Logger(subsystem: "io.github.krszozda.latawiec", category: "store")

/// A purchase the store has charged for, waiting to be told it was
/// delivered.
///
/// `finish()` is the shell's promise to StoreKit that the customer has
/// what they paid for, so it must wait for the server to answer: an
/// unfinished transaction comes back on the next launch, a finished one
/// the server never heard about is gone.
struct StorePurchase {
    let product: String
    /// The signed JWS the server verifies with Apple. The shell does not
    /// decide what it is worth.
    let receipt: String
    private let transaction: StoreKit.Transaction

    init(product: String, receipt: String, transaction: StoreKit.Transaction) {
        self.product = product
        self.receipt = receipt
        self.transaction = transaction
    }

    /// What the action POSTs. Deliberately only the receipt: a product id
    /// in the request would be the client's word, and a handler that
    /// trusted it would grant whatever a patched client asked for.
    var values: [String: String] { ["receipt": receipt] }

    func finish() async {
        await transaction.finish()
    }
}

/// What a tap on a Purchase can end in.
enum PurchaseOutcome {
    case bought(StorePurchase)
    /// The user backed out, or the purchase is waiting on someone else —
    /// a parent's approval. Neither is worth a message, and an approval
    /// that comes later arrives through ``Store/deliveries()``.
    case nothingToReport
    case failed(message: String)
}

/// The App Store side of the DSL's Purchase.
///
/// StoreKit is part of the system, so buying costs the app no dependency;
/// what it costs the developer is a product in App Store Connect with a
/// matching id, and a server that verifies receipts.
enum Store {
    /// A device with no store behind it — a plain simulator, a phone with
    /// no network — can leave the lookup hanging, and a button that hangs
    /// says nothing at all.
    private static let lookupTimeout: TimeInterval = 15

    private struct Unreachable: Error {}

    /// Raced outside a task group on purpose: a group waits for every
    /// child, so a lookup that ignores cancellation would hold the timeout
    /// hostage — which is the exact case this exists for.
    private static func lookUp(_ product: String) async throws -> Product? {
        let lookup = Task { try await Product.products(for: [product]) }
        let timeout = Task {
            try await Task.sleep(nanoseconds: UInt64(lookupTimeout * 1_000_000_000))
            lookup.cancel()
        }
        defer { timeout.cancel() }
        do {
            return try await lookup.value.first
        } catch is CancellationError {
            throw Unreachable()
        }
    }

    static func buy(_ product: String) async -> PurchaseOutcome {
        do {
            guard let item = try await lookUp(product) else {
                // Almost always a typo or a product that was never
                // submitted, so name it rather than saying "failed".
                return .failed(message: "The store has no product called \(product)")
            }
            switch try await item.purchase() {
            case let .success(verification):
                return received(verification)
            case .userCancelled, .pending:
                return .nothingToReport
            @unknown default:
                // Money: an outcome this build does not understand is
                // worth a word, not silence.
                log.warning("unknown purchase result for \(product)")
                return .failed(message: "The purchase could not be completed")
            }
        } catch is Unreachable {
            return .failed(message: storeUnreachable)
        } catch {
            log.warning("purchase of \(product) failed: \(String(describing: error))")
            return .failed(message: "The purchase could not be completed")
        }
    }

    /// Everything the store charges for outside a tap: an Ask to Buy
    /// approved later, a purchase made on another device or while the app
    /// was closed, a redeemed code — plus anything left unfinished by an
    /// earlier run, which StoreKit replays here on launch.
    static func deliveries() -> AsyncStream<StorePurchase> {
        AsyncStream { continuation in
            let watcher = Task {
                for await verification in Transaction.updates {
                    if case let .bought(purchase) = received(verification) {
                        continuation.yield(purchase)
                    }
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in watcher.cancel() }
        }
    }

    private static func received(
        _ verification: VerificationResult<StoreKit.Transaction>
    ) -> PurchaseOutcome {
        switch verification {
        case let .verified(transaction):
            // The device checked Apple's signature; the server must check
            // it too, which is what the receipt is for.
            return .bought(
                StorePurchase(
                    product: transaction.productID,
                    receipt: verification.jwsRepresentation,
                    transaction: transaction
                )
            )
        case let .unverified(_, error):
            // A receipt the device itself distrusts is not worth sending.
            log.warning("unverified transaction: \(String(describing: error))")
            return .failed(message: "The store's receipt could not be trusted")
        }
    }
}

/// Both shells word it the same way, so the docs can promise it.
let storeUnreachable = "The store could not be reached"
