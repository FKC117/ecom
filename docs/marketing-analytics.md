# Marketing analytics

The selected Sanjilas website Meta Pixel ID is `644965951111560`.
The existing GA4 web stream for `https://sanjilas.com` uses measurement ID
`G-HL7GG88HT2` (property `411610578`, stream `6282251106`). Both IDs are saved
in local Site Settings; both provider enable switches remain off.
Configure it in Site Settings → Marketing analytics in Django admin or `/control/`.
The ID and enable switches are backend settings. Both providers default to off.
The Google field accepts a GA4 `G-…` measurement ID, not a GTM container ID.
Reuse the verified existing Google property when enabling it; do not create a
duplicate property or install both direct GA4 and an equivalent GTM tag.

Apply migration 0074 and rebuild the frontend before using these settings.
No Meta access token is needed for browser Pixel events. This implementation does
not configure Conversions API. Automatic advanced matching remains off in Meta;
the application supplies no customer matching parameters.

## Events

- PageView / page_view: once per storefront document, after configuration loads.
- ViewContent / view_item: product detail and selected variant, deduplicated within
  the document for the same item.
- AddToCart / add_to_cart: successful reservation additions and quantity increases.
  Django calculates the added quantity under the existing row locks. Failed writes,
  removals and quantity decreases do not emit AddToCart.
- InitiateCheckout / begin_checkout: checkout opens, once per cart reservation
  window per document. Restored checkout drafts count as checkout entry.
- Purchase / purchase: successful order placement, including cash on delivery and
  orders awaiting payment verification. This measures placed orders, not collected
  revenue. Simulated orders are excluded. The order ID provides an event ID and
  browser-storage deduplication across retries. Disabled storage limits this to
  in-memory deduplication. Order history and invoice visits do not emit purchases.

Amounts and quantities originate from Django. Purchase values include shipping;
cart-add values include added merchandise only. SKU is the content ID; any future
Meta catalog must use these same SKU IDs. No email, phone, address, internal
commerce browser key or checkout draft is explicitly included in event payloads.
The third-party libraries still collect their own browser/network context.
Tracking is initialized only by the storefront, not account, invoice or control
pages. Ad blockers can prevent browser events, and browser events are not a full
customer directory. Google stays disabled until deployment and live verification.

## Abandonment

Cart journeys are first-party staff-only records available from the Django admin
registry and the generated React admin model directory. Each successful cart
write snapshots its catalog items, subtotal and fixed reservation deadline.
Checkout draft saves mark checkout entry without retaining contact information
in the journey. The original cart still belongs to its authenticated customer.

An open journey becomes **abandoned** when its reservation deadline passes
without a successful order. Status is calculated at read time; no scheduler or
browser-close event is needed. Emptying a live cart marks it **emptied**. Successful
checkout marks it **converted**; later cancellation does not turn it into an
abandoned cart. New reservation windows keep separate history. Reads and draft
saves do not extend stock holds. Existing historical carts are not backfilled.
Journey history is retained until a separate retention policy is implemented.
The Django admin offers a journey-status filter. React lists use the existing
registry adapter and its permissions; no new frontend model allowlist exists.

For Meta retargeting, create a website custom audience including AddToCart and/or
InitiateCheckout and excluding Purchase over the chosen audience window. The
website does not claim to send an official Meta CartAbandoned standard event.
Audience membership is a platform estimate and can differ from first-party
journeys. Audiences and ad-account sharing still need configuration in Meta.

## Go-live verification

Enable the selected Pixel ID on the deployed site, open Meta Test events, then
verify PageView, product view, successful add and checkout start. Test a genuine
order separately; dummy payments must emit no Purchase. Check that cart refresh,
quantity decrease, failed stock writes and history/invoice visits do not create
purchase/add events. Verify a journey's abandoned status after its deadline, and
that converted journeys stay converted. Check GA4 DebugView after the existing
Google ID is supplied. Browser testing and production deployment are separate
from local build and automated checks.
