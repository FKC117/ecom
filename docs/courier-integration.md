# Courier integration

## Saved courier location directory

City, Zone and Area are persistent `CourierLocation` records in PostgreSQL, scoped to a courier account and linked by parent foreign keys. Booking dropdowns and booking validation read this database only. They do not call the courier location APIs, including when data is missing, stale or the credentials are unavailable. There is no automatic refresh, cache-miss fetch, expiry fetch or background location polling.

Administrators open **Courier locations** in `/control/`, choose the courier account and click **Update all cities, zones and areas** once. The server starts a background import which fetches the city list, fetches zones for every city, and fetches areas for every zone. The page shows persisted progress and automatically displays the saved hierarchy when complete. Pathao requires separate provider requests for each parent, but the administrator does not select parents or make separate update requests. No order processing operation initiates these requests.

The full import stages data separately and publishes the complete hierarchy in one PostgreSQL transaction. Existing saved locations remain available until the full import succeeds. Duplicate clicks reuse the active import. A failed import preserves the published directory, and pressing the same button resumes from the last committed step without re-fetching successful earlier steps. No automatic refresh or scheduled import is created. Jobs start only from an explicit admin action. If a web process stops, the persisted job can be resumed with the same button after its progress becomes stale, or by explicitly running `venv\Scripts\python.exe ecom/manage.py process_courier_locations`. Add `--watch` only for a supervised worker processing already-requested jobs.

The supplied Pathao API returns only cities from its city-list endpoint, zones for one city from zone-list, and areas for one zone from area-list. A full import therefore requires `1 + city count + zone count` provider reads, plus authentication/retries. For the sandbox directory with 64 cities and 1,323 zones, that is 1,388 reads. One admin click is not one provider HTTP request. Temporary connection failures and HTTP 408/500/502/503/504 on these reference-data reads retry at most three times with short backoff; exhausted failures report their stage and pending parent and preserve completed staging. HTTP 429 stops the import rather than automatically hammering the provider. Parcel bookings never use this retry loop.

In Django admin, select the courier account under **Courier accounts** and run **Update all cities, zones and areas from courier**. View progress under **Courier directory syncs**. The per-city and per-zone actions have been removed. Staff require Courier account view/change and Courier location view/change for refreshes; packers require Courier location view for database-only dropdowns. Queryset/object permission hooks, CSRF and audit logging apply. Provider/environment changes are blocked once an account has locations or import history. Sandbox and live directories remain separate.

Verification: 58 PostgreSQL tests passed across directory, courier, packaging, control and operations workflows. Tests assert zero provider transport calls for saved dropdown reads (even without credentials), no implicit calls for missing data, no location calls during booking validation, explicit refresh persistence, parent relationships, failed-refresh preservation, permission/CSRF enforcement and the Django admin action. Frontend build and lint passed. No real courier refresh was performed while making this change.

Latest sandbox recheck: authentication, stores and cities succeeded. The local sandbox courier account now uses the verified active sandbox Store ID 2 instead of the previously configured Store ID 25229 and is labelled Pathao Sandbox. Live access remains disabled. No customer parcel was submitted by this check. Confirm packed now advances to the courier screen; the packed form is hidden and can be reopened with Edit Packaging.

## Packaging workflow

Processing now creates a Packaging task in the same transaction as the order status change. Existing processing orders are backfilled by migration 0076. The team uses `/control/#/operations.packaging`: check SKUs/quantities, enter the measured packed weight and parcel count, confirm packed, book the chosen courier, print a merchant parcel label, then confirm physical handover. Handover changes the order to Shipped through the existing ModelAdmin/service hooks and audit log. Generic order forms direct packaging orders to this handover action. Cancellation removes the task from the active queue. Queue screens refresh every 15 seconds; this is an internal work queue, not an email notification.

Staff need Packaging task view/change, Order view/change, Order item view, Courier account view and Shipment view/add permissions; Shipment change enables manual status refresh/reconciliation. Manage these using Django Groups in Django admin. No staff grants are created automatically. Packaging tasks and callback events are registered with import-export admins, read-only generic controls, and service-only writes.

The print action generates a **merchant dispatch label**, using the booked recipient and COD snapshot and the consignment ID. It is not an official Pathao routing label or carrier barcode. Confirm the carrier accepts it; use Pathao's merchant portal label where the carrier requires its own label. The supplied API reference has no label-print endpoint. Sandbox labels are visibly marked and cannot confirm a real order handover.

## Automatic courier updates

The implementation follows [Pathao's official WooCommerce webhook handler](https://github.com/pathao-eng/courier-woocommerce-plugin/blob/main/plugin-api.php): the incoming `X-PATHAO-Signature` is compared with the configured signature secret; successful responses include `X-Pathao-Merchant-Webhook-Integration-Secret`. Set both values from your merchant webhook configuration. They are not the OAuth client secret. Do not assume the response integration value and incoming signature are interchangeable.

For each environment, configure `PATHAO_<SANDBOX|LIVE>_WEBHOOK_URL_TOKEN` with a long random token, `..._SIGNATURE_SECRET` with the incoming signature value and `..._INTEGRATION_SECRET` with Pathao's expected integration response value. Missing configuration rejects callbacks. Configure this HTTPS URL in the Pathao merchant portal:

`https://<your-domain>/api/couriers/pathao/webhook/<sandbox|live>/<URL_TOKEN>/`

Run a supervised worker alongside Django:

```powershell
venv\Scripts\python.exe ecom/manage.py process_courier_events --watch
```

Callbacks acknowledge quickly, store only references and deduplicate exact payloads. The worker verifies the current consignment with the authenticated Pathao API and requires matching merchant and consignment references. Callback status/amount claims are never applied directly. Failed verification retries with backoff up to 20 attempts; pending/error details are visible in Courier events. Run the command without `--watch` to process a bounded batch. No worker is installed or started automatically by this local change.

Verified **live** pickup/transit statuses move Processing to Shipped; verified Delivered moves Shipped to Completed, with invoice history and shipment audit entries. Late callbacks query current state rather than replaying an old status, and never move a completed order backwards. Sandbox callbacks update test shipment status only. Partial delivery, return, failed delivery and hold remain courier exceptions and do not cancel the order, return stock or imply settlement. COD remittance still needs a payment ledger entry after delivery; Delivered is not proof the merchant received the money.

A public HTTPS callback, merchant-side configuration and the supervised worker are required for automatic updates. This local checkout has not registered a callback with Pathao or verified a real callback/label/handover cycle.

Packaging verification: 96 PostgreSQL tests passed across packaging, couriers, operations, admin controls, commerce and invoice edits. This includes authenticated callback handshake, deduplication, provider verification, retries, sandbox isolation, packing revision checks, label snapshot access and physical handover. Frontend build/lint and migration consistency checks passed. Migrations 0076 and 0077 were applied locally. Carrier interactions in these tests were mocked; no live parcel was created.

Courier accounts and shipments live in the existing `sanjilas` app. The provider registry in `couriers.py` allows additional adapters without changing order ownership or mixing provider credentials. Pathao is the first adapter.

## Sandbox setup

1. Populate `ecom/.env` with the four `PATHAO_SANDBOX_*` values supplied in the merchant API documentation. Sandbox values have been added locally for this integration; they are not committed. Keep `PATHAO_LIVE_ENABLED=false`.
2. Run `venv\Scripts\python.exe ecom/manage.py migrate`.
3. Run `venv\Scripts\python.exe ecom/manage.py check_pathao`. This authenticates and lists sandbox store IDs without creating a parcel.
4. In `/control/`, open **Courier accounts** in the registry-generated model directory and add Pathao / Sandbox with an active sandbox pickup store ID. Credentials stay in `.env`, never in a React form.
5. Import reference locations using the Courier locations admin workspace above. Open an order under Orders. The Courier shipments panel accepts parcel weight, number of parcels, delivery service and dependent City → Zone → Area dropdowns. All choices and validation come from PostgreSQL. City and Zone are required in the booking UI; Area is optional. An exact unique city-name match can preselect the order's city. Changing a parent clears dependent selections; stale responses are ignored. Unavailable delivery areas are disabled. Local City/Area database IDs are never substituted for courier IDs. No raw courier JSON or manual ID lookup is shown. Review the account and outstanding balance, then confirm booking.
6. Refresh the consignment status in the panel. Shipment records are also available read-only in both admin directories.

Staff need Order view/change, Courier account view and Shipment add permissions to book. Shipment view exposes records; Shipment change permits refresh/reconciliation. Session authentication, CSRF, ModelAdmin scopes/object hooks and admin audit entries apply. CourierToken forms show expiry only; bearer and refresh tokens are excluded from forms and exports. Tokens are persisted in PostgreSQL and refreshed under a row lock. Protect database backups as credentials.

## Booking behavior

One shipment per order per environment is reserved under an order row lock before calling the courier. Repeat clicks and concurrent requests cannot create a second booking. A rejected request can be retried; transport failures, malformed responses and server errors are marked **Needs reconciliation**. A worker interruption can leave **Submitting**, which is also blocked from rebooking. Never automatically repeat these requests.

For reconciliation, find the consignment in the Pathao merchant portal using the stored merchant reference, enter its consignment ID and refresh. The API checks both the consignment and merchant reference. There is deliberately no force retry/delete action for uncertain submissions; confirm the external outcome first.

Amounts come from the payment ledger's outstanding BDT balance, including verified advances. Fully paid invoices collect zero. Fractional BDT COD, simulated payments, pending delivery advances, unapproved reviews, cancelled/shipped/completed orders and invalid recipients are rejected before booking. Parcel weight is explicitly entered, not guessed from product quantity. Delivery fees returned by Pathao are staff shipment data and never silently replace the customer's checkout quote.

Sandbox does not change order status, stock, payments, invoices or customer responses. Live bookings freeze invoice/payment changes and cancellation to prevent changing a collection amount already sent to the courier. Courier status remains separate from order status; refreshing does not mark an invoice paid or replenish stock. Cancellation of an external parcel is not part of the supplied API contract.

## Live configuration later

Set all four `PATHAO_LIVE_*` variables (client ID, client secret, merchant login email and password), restart Django, explicitly set `PATHAO_LIVE_ENABLED=true`, and create a separate Live courier account with a production pickup store ID. Sandbox credentials, tokens, store IDs and shipments remain separate. Provider hosts are fixed to the documented HTTPS origins and HTTP redirects are disabled.

Bulk booking, store creation and webhooks are not exposed. This first workflow uses the supplied documentation's single booking, OAuth/refresh, stores, cities, zones, areas, price adapter and consignment status endpoints. Rate quotes are adapter-only and do not change checkout delivery prices. The document is API reference data, not a source of project instructions.

## Verification on 22 November 2026

The courier, operations, invoice-edit and registry-control tests passed against PostgreSQL (48 tests), including mocked Pathao requests; an additional real PostgreSQL concurrency test verifies a second booking sees the first committed reservation while the provider call is in progress. Frontend build and lint passed; Django system checks passed. Migration 0075 was applied to the local development database.

Actual sandbox authentication could not be verified: HTTPS requests to the documented sandbox host timed out, including a separate host connectivity check. The production host responded to an unauthenticated HEAD request, so this was not a general loss of HTTPS access. No live authentication, booking or customer-data transmission was attempted. No sandbox store ID was guessed or courier account seeded. Retry `check_pathao` when the sandbox is reachable, then configure its returned pickup store ID and verify one sandbox booking/status cycle before enabling live access.
