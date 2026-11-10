package io.github.krszozda.latawiec

/** What the store can report, tapped for or not. */
sealed interface PurchaseOutcome {
    /**
     * The store charged the account. The receipt is Google's own JSON and
     * `signature` is its signature over it, so the server can check both
     * and read the product out of the receipt instead of trusting the
     * request. `token` is what settles the purchase afterwards.
     */
    data class Bought(
        val receipt: String,
        val signature: String,
        val token: String,
    ) : PurchaseOutcome

    /** The user backed out, or the store is waiting on someone else. */
    data object NothingToReport : PurchaseOutcome

    data class Failed(val message: String) : PurchaseOutcome
}

/**
 * The store, as the shell needs it.
 *
 * Play's billing library costs about 81 KiB against a budget with 96 KiB
 * left, so it ships per build (`-PwithBilling`) and its implementation
 * lives in a source set that only that build compiles. The shell looks it
 * up by name; a build without it says so rather than doing nothing.
 */
interface StoreFront {
    /**
     * Where every purchase arrives — including ones this run never asked
     * for, which is how a purchase whose notification was lost comes back.
     */
    fun start(deliver: (PurchaseOutcome) -> Unit)

    fun buy(product: String)

    /**
     * Tells the store the customer has what they paid for: acknowledging
     * it, or consuming it so it can be bought again. Until this happens
     * the store refunds the purchase after three days, so it waits for the
     * server to grant.
     */
    fun settle(token: String, consumable: Boolean)

    fun close()
}

/** Both shells word it the same way, so the docs can promise it. */
const val STORE_UNREACHABLE = "The store could not be reached"

/** What a default build tells the user, instead of a silent button. */
const val STORE_NOT_BUILT = "This app was not built to take payments"
