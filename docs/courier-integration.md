# Courier integration

Courier accounts and shipments live in the existing `sanjilas` app. The provider registry in `couriers.py` allows additional adapters without changing order ownership or mixing provider credentials. Pathao is the first adapter.

## Sandbox setup

1. Populate `ecom/.env` with the four `PATHAO_SANDBOX_*` values supplied in the merchant API documentation. Sandbox values have been added locally for this integration; they are not committed. Keep `PATHAO_LIVE_ENABLED=false`.
2. Run `venv\Scripts\python.exe ecom/manage.py migrate`.
3. Run `venv\Scripts\python.exe ecom/manage.py check_pathao`. This authenticates and lists sandbox store IDs without creating a parcel.
4. In `/control/`, open **Courier accounts** in the registry-generated model directory and add Pathao / Sandbox with an active sandbox pickup store ID. Credentials stay in `.env`, never in a React form.
5. Open an order under Orders. The Courier shipments panel accepts parcel weight, number of parcels, service and optional Pathao location IDs. Review the account and outstanding balance, then confirm the booking. Stores and location lookup are available in the panel. Pathao can detect omitted location IDs from the full address. Local City/Area database IDs must never be used as Pathao IDs.
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
