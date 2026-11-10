package io.github.krszozda.latawiec

import android.app.Activity
import android.util.Log
import com.android.billingclient.api.AcknowledgePurchaseParams
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.ConsumeParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams

private const val STORE_TAG = "LatawiecStore"

/**
 * The Play side of the DSL's Purchase, present only in a `-PwithBilling`
 * build.
 *
 * Play's answer can arrive when nothing is waiting — the network dropped
 * during the purchase, a family member approved it on another device, the
 * app was not running — so every connection re-reads what the account
 * owns and delivers it through the same path a tap would.
 */
class PlayStore(private val activity: Activity) : StoreFront {

    /** What a tap is waiting for, if anything. */
    private var pending: String? = null

    /** Where every purchase goes, tapped for or not. */
    private var deliver: ((PurchaseOutcome) -> Unit)? = null

    private val client: BillingClient = BillingClient.newBuilder(activity)
        .enablePendingPurchases()
        .setListener(
            PurchasesUpdatedListener { result, purchases ->
                when (result.responseCode) {
                    BillingClient.BillingResponseCode.USER_CANCELED -> {
                        pending = null
                        answer(PurchaseOutcome.NothingToReport)
                    }
                    BillingClient.BillingResponseCode.OK -> hand(purchases.orEmpty())
                    else -> {
                        pending = null
                        answer(failure(result))
                    }
                }
            },
        )
        .build()

    override fun start(deliver: (PurchaseOutcome) -> Unit) {
        this.deliver = deliver
        connect { }
    }

    private fun answer(outcome: PurchaseOutcome) {
        deliver?.invoke(outcome)
    }

    /**
     * Purchases Play has charged for, whether or not this run asked. A
     * purchase reported twice is harmless: the server verifies the receipt
     * and must reject a replay anyway.
     */
    private fun hand(purchases: List<Purchase>) {
        val wanted = pending
        for (purchase in purchases) {
            if (purchase.purchaseState != Purchase.PurchaseState.PURCHASED) continue
            if (wanted != null && purchase.products.contains(wanted)) pending = null
            answer(
                PurchaseOutcome.Bought(
                    // Self-describing on purpose: the server can check
                    // Google's signature over this exact JSON, and read the
                    // product out of it rather than trusting the request.
                    receipt = purchase.originalJson,
                    signature = purchase.signature,
                    token = purchase.purchaseToken,
                ),
            )
        }
        // A tap whose purchase is not in this answer got nothing.
        if (wanted != null && pending == wanted) {
            pending = null
            answer(PurchaseOutcome.NothingToReport)
        }
    }

    /**
     * Play revokes a purchase that is not acknowledged within three days,
     * so this happens once the server has granted it — which is also when
     * a consumable may be bought again.
     */
    override fun settle(token: String, consumable: Boolean) {
        if (consumable) {
            client.consumeAsync(
                ConsumeParams.newBuilder().setPurchaseToken(token).build(),
            ) { result, _ ->
                if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                    Log.w(STORE_TAG, "consume failed: ${result.debugMessage}")
                }
            }
            return
        }
        client.acknowledgePurchase(
            AcknowledgePurchaseParams.newBuilder().setPurchaseToken(token).build(),
        ) { result ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                Log.w(STORE_TAG, "acknowledge failed: ${result.debugMessage}")
            }
        }
    }

    private fun failure(result: BillingResult): PurchaseOutcome = when (result.responseCode) {
        BillingClient.BillingResponseCode.BILLING_UNAVAILABLE,
        BillingClient.BillingResponseCode.SERVICE_DISCONNECTED,
        BillingClient.BillingResponseCode.SERVICE_UNAVAILABLE,
        -> PurchaseOutcome.Failed(STORE_UNREACHABLE)
        else -> {
            Log.w(STORE_TAG, "billing failed ${result.responseCode}: ${result.debugMessage}")
            PurchaseOutcome.Failed("The purchase could not be completed")
        }
    }

    private fun connect(then: () -> Unit) {
        if (client.isReady) {
            then()
            return
        }
        client.startConnection(
            object : BillingClientStateListener {
                override fun onBillingSetupFinished(result: BillingResult) {
                    if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                        pending = null
                        answer(failure(result))
                        return
                    }
                    // Google asks for this on every connection: it is the
                    // only way a purchase whose notification was lost ever
                    // reaches the app.
                    recover()
                    then()
                }

                override fun onBillingServiceDisconnected() {
                    if (pending != null) {
                        pending = null
                        answer(PurchaseOutcome.Failed(STORE_UNREACHABLE))
                    }
                }
            },
        )
    }

    private fun recover() {
        client.queryPurchasesAsync(
            QueryPurchasesParams.newBuilder()
                .setProductType(BillingClient.ProductType.INAPP)
                .build(),
        ) { result, purchases ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK) hand(purchases)
        }
        client.queryPurchasesAsync(
            QueryPurchasesParams.newBuilder()
                .setProductType(BillingClient.ProductType.SUBS)
                .build(),
        ) { result, purchases ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK) hand(purchases)
        }
    }

    override fun buy(product: String) {
        if (pending != null) {
            // Play's sheet is already up for this; a second flow would
            // orphan the first purchase.
            return
        }
        pending = product
        connect { lookUp(product) }
    }

    /** A product id says nothing about its type, so ask for both. */
    private fun lookUp(product: String) {
        query(product, BillingClient.ProductType.INAPP) { item ->
            if (item != null) {
                launchFlow(item)
                return@query
            }
            query(product, BillingClient.ProductType.SUBS) { subscription ->
                if (subscription != null) {
                    launchFlow(subscription)
                } else {
                    pending = null
                    // Almost always a typo or a product that was never
                    // published, so name it rather than saying "failed".
                    answer(PurchaseOutcome.Failed("The store has no product called $product"))
                }
            }
        }
    }

    private fun query(product: String, type: String, found: (ProductDetails?) -> Unit) {
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(
                listOf(
                    QueryProductDetailsParams.Product.newBuilder()
                        .setProductId(product)
                        .setProductType(type)
                        .build(),
                ),
            )
            .build()
        client.queryProductDetailsAsync(params) { result, details ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                pending = null
                answer(failure(result))
                return@queryProductDetailsAsync
            }
            found(details.firstOrNull())
        }
    }

    private fun launchFlow(item: ProductDetails) {
        val offer = item.subscriptionOfferDetails?.firstOrNull()?.offerToken
        val params = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(
                listOf(
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                        .setProductDetails(item)
                        .apply { if (offer != null) setOfferToken(offer) }
                        .build(),
                ),
            )
            .build()
        val result = client.launchBillingFlow(activity, params)
        if (result.responseCode != BillingClient.BillingResponseCode.OK) {
            pending = null
            answer(failure(result))
        }
    }

    override fun close() {
        deliver = null
        pending = null
        client.endConnection()
    }
}
