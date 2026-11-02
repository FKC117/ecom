# Sanjilas

Django backend (`ecom/`) and a separate React frontend (`frontend/`), with PostgreSQL.
All storefront pages belong in React. Django exposes JSON under `/api/` and retains
its built-in administration at `/admin/`.

## Local development (PowerShell, from D:\ecom)

Backend:

```powershell
.\venv\Scripts\python.exe -m pip install -r ecom\requirements.txt
# For a new checkout, copy ecom/.env.example to ecom/.env and fill in credentials.
# PostgreSQL must be installed and running.
# Only if the configured database does not exist:
.\venv\Scripts\python.exe ecom\bootstrap_db.py
.\venv\Scripts\python.exe ecom\manage.py migrate
.\venv\Scripts\python.exe ecom\manage.py runserver 127.0.0.1:8000
```

Frontend, in a second terminal:

```powershell
cd D:\ecom\frontend
npm ci
npm run dev
```

Open http://localhost:5173. React requests `/api/health/` through Vite's
proxy to Django. That endpoint reports application liveness, not database readiness.
No CORS package is needed with this same-origin proxy. Keep Django CSRF protection
for state-changing requests; implement token handling when adding authentication/forms.
The `.env` stays private and existing environment variables take precedence over it.
`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` accept comma-separated values.

## Checks

```powershell
.\venv\Scripts\python.exe ecom\manage.py check
.\venv\Scripts\python.exe ecom\manage.py migrate --check
cd frontend
npm run lint
npm run build
```

## Deployment

Route `/` to Django: it serves the built React document and injects Site Settings
metadata for crawlers. Route `/api/`, `/admin/`, `/llms.txt`, and `/llms-full.txt`
to Django too. Serve `/assets/` from `frontend/dist/assets` and configure Django
static files and uploaded `/media/` separately on the same origin.
Vite's development proxy does not ship in the production build. Set `DEBUG=False`,
a strong `SECRET_KEY`, production hosts and trusted HTTPS origins before deploying.
The homepage supports collection browsing, search and product detail dialogs.
Cart, checkout and customer authentication are not implemented yet.

## Site settings

Edit the single record in Django admin under Sanjilas > Site settings. It owns the
site name, tagline, logos, favicon, Apple icon, footer text, canonical URL, SEO,
Open Graph and Twitter/X metadata/images, and both public LLM documents. Use PNG
or ICO for the favicon. React loads `/api/site-settings/`; no branding is hardcoded
in the frontend. The LLM fields are served as plain text at `/llms.txt` and
`/llms-full.txt`. Blank fields produce empty text documents. All these fields are
public, so store only content intended for publication.

Development through Vite updates metadata in JavaScript. For crawler-visible initial
metadata, run `npm run build` and visit Django's root URL. Production must route the
document through Django rather than serve the raw build index.

Every new concrete Sanjilas model is automatically registered with import/export.
Custom admins must inherit `ImportExportModelAdmin`. Site settings imports always
update ID 1, validate the model, and reject other IDs. Import/export includes image
storage paths, not the image binary files: migrate/back up media separately.
Import requires change permission; export requires view permission.

## Jewellery homepage and themes

All homepage text is editable in admin > Sanjilas > Home page, including navigation,
button text, search/empty states, and accessibility labels in the JSON `labels` field.
Collections and Products have their own admin screens with import/export. Inactive
collections and products are excluded from the public API. Featured products appear
in the initial home edit; choosing a collection shows its active products.

Site settings > Theme and contact selects Champagne Gold, Rose Quartz, Emerald
Atelier, Midnight Sapphire, or Pearl & Platinum, and the initial light/dark mode.
Each palette has both modes. Customers only see the light/dark toggle, which remembers
their preference in localStorage. There is no customer-facing palette selector.
All authored CSS, including the ten variants, lives in `frontend/src/index.css`.
Add a contact email to enable email enquiries; otherwise the contact CTA browses
the jewellery. No email is sent by opening a detail dialog.

`python ecom/manage.py seed_homepage` creates optional editable preview records
without overwriting existing data. The installed sample items are examples, not a
live stock/price list. Replace descriptions and upload actual product imagery before
launch. Preview photographs are stored locally in `ecom/media/homepage/preview`.
They are independent media files and are not included in model exports.

Preview photography: Unsplash images `photo-1673131158657-4404fd1f041a` (Isaline Baslé),
`photo-1682823544362-b751e260e33c` (Natali Hordiiuk),
`photo-1708221269651-25d29e63e8b1` (Oscar Ramirez),
`photo-1605100804763-247f67b3557e`, `photo-1599643477877-530eb83abc8e`, and
`photo-1611591437281-460bfbe1220a`.

## React administration

Open `/control/` on the Django or Vite development server. The existing `/admin/`
remains available. The React panel uses Django sessions and CSRF tokens; credentials
and authentication tokens are never stored in localStorage. Login requires an active
staff or superuser account. Superusers see every registered model; staff see only
models allowed by their Django permissions.

To grant access in Django admin:

1. Create a Group for a role and assign its model view/add/change/delete permissions.
2. Mark the user active and staff, then assign the Group (or direct permissions).
3. Sign in at `/control/`. Changes to permissions apply on the next backend request.

The React model directory is generated from `admin.site` registration; no frontend
model allowlist exists. It reuses ModelAdmin querysets, object permission checks,
ModelForms, fieldsets/read-only fields, validation, save/delete hooks, and audit logs.
Lists are paginated. Forms support images/files, choices, searchable relations,
many-to-many selections, JSON, booleans, dates and split date/time fields. Deletion
requires a related-record preview and confirmation and respects protected relations.
Account and role writes in React require a superuser; a staff account with auth-model
permissions can inspect them but cannot use this panel to grant itself more access.
Existing-user password changes continue to use Django admin.

CSV exports use the registered django-import-export resource and scoped queryset.
Import links open Django's existing preview/confirmation flow. Custom inline formsets,
custom actions and unsupported compound widgets are not silently emulated: the panel
provides a Django admin link for these advanced controls, and blocks incomplete saves.
When adding such custom controls, add their React support as part of the model work.

All panel labels/messages come from `SiteSettings.control_labels`, and field/model
labels come from Django. Branding, palette and mode use the existing shared design
system in `frontend/src/index.css`. Production routing must send `/control/` to Django
along with the API/admin routes and continue serving `/assets/` from the React build.
For a multi-worker deployment, configure a shared Django cache so the sign-in attempt
limit is coordinated across workers.

## WebP image engine

All project image fields use `sanjilas.image_fields.WebPImageField`. New binary uploads
from React admin, Django admin, or model file saves are decoded and converted to WebP.
JPEG/JPG, PNG, WebP, GIF, TIFF, BMP, ICO, AVIF and HEIC/HEIF are supported; SVG/PDF and
other non-photo formats are rejected. Animated/multi-page files use their first frame.
Uploads are limited to 15 MB, 32 megapixels and 16,000 pixels per side. The pipeline
corrects EXIF rotation, converts valid colour profiles to sRGB, preserves transparency,
and omits source EXIF/GPS/XMP metadata from generated files.

The stored master is at most 2560px on its longest edge. Smaller WebP versions at
320/640/960/1280/1600px widths are generated only when smaller than the master; nothing
is upscaled. `IMAGE_*` settings control limits and compression quality. The `webp1`
filename policy freezes the derivative widths for existing files. Add a new policy
version rather than changing the meaning of old filenames. Public APIs return image
dimensions and srcset metadata; React's shared `ResponsiveImage` uses them.

React admin image fields provide **Edit image** with an immediate browser canvas preview
for crop, rotate, flip, brightness, contrast and maximum output width. **Adjust crop**
provides a draggable selection with resize handles, keyboard movement and a live
cropped result. The browser loads a neutral, colour-normalized source once; changing
controls does not send preview requests. Large images use a bounded-resolution local
preview; final compression and pixel precision come from the backend on **Apply edits**.
Preview requests check model/object permissions, use CSRF and return uncached WebP
bytes without saving files. **Apply edits** stages adjustments; **Save changes** commits a new
immutable image filename. Django admin exposes the same transformations in expandable
image controls; enable the adjustments before saving. New uploads don't require that
checkbox to receive automatic conversion.

Raw uploaded originals are not persisted. Previous stored image versions and legacy
files are retained; replacing/clearing a field does not automatically delete files
that may still be referenced elsewhere. Database failures after storage writes may
leave unused generated files; any future cleanup must check references before deletion.
Model exports contain image paths, not image data. Import paths should refer to files
already present in media storage. Favicons/Apple icons store WebP masters and generate
small PNG compatibility files used by public branding URLs.

Convert older image fields without removing their source files:

```powershell
.\venv\Scripts\python.exe ecom\manage.py convert_images
.\venv\Scripts\python.exe ecom\manage.py convert_images --apply
```

The first command validates/estimates conversion without writing files. The second
converts each image field, preserving unrelated record values and its legacy source.
Already processed images are skipped, so rerunning it is safe.

`deploy/nginx-media.conf.example` provides media/assets/static aliases, image MIME
types, read-only media serving, no directory listing, nosniff headers, immutable caching
and a 20 MB request-body limit. Adjust filesystem aliases to the actual deployment,
include it inside the Nginx server block, and validate with `nginx -t` before reloading.
It is a deployment template; no server has been changed by this local implementation.

## Product catalog

Products now support SKU, regular price, percentage/fixed discounts, tags, material,
gemstone, care instructions and optional stock tracking. Final prices are calculated
with Decimal rounding in Django; a blank price remains price on request.

In `/control/`, add a product under Products and save it. Reopen the product to add
Product variants, Product features and Product images from its related sections.
These sections come from the Django admin registry and respect its permissions.
Tags can be assigned to products and variants. Variants use customer-facing names,
unique SKUs and optional size, colour/finish, material and gemstone values.

A blank variant price inherits the product regular price. A variant inherits the
product discount unless Override discount is enabled. Enable it with No discount
to exempt that variant, or supply a variant percentage/fixed amount. Invalid prices,
discounts, duplicate SKUs and negative stock are rejected on normal saves/imports.
Keep currency on the parent product. Stock tracking defaults off for existing
products and on for new products and variants. Zero tracked stock is sold out unless backorders
are enabled. Cart reservations and COD checkout are described below.

The storefront renders active variants, active tags and active gallery images,
features, availability, regular/sale prices and a variant selector. Product cards
show the lowest currently available variant price, with From when prices differ.
No new Django app was created; all catalog records use ImportExportModelAdmin and
are managed through Products in React. Their standalone React menu/dashboard entries
are hidden via ModelAdmin metadata. Shared tags are managed in Django admin and
assigned on React product/variant forms.


## Cart reservations and cash-on-delivery orders

Enable stock tracking and enter actual on-hand quantities for simple products, or
for each variant when a product has variants. Existing products are not assigned
invented stock. Untracked/unpriced products remain available for enquiries.
Set checkout currency, shipping fee, reservation minutes (default 20), and whether
cash on delivery is enabled in Site Settings.

Signed-in customers add items using the product popup and manage their bag from
the header. Cart additions reserve stock immediately; stock is held per product
or exact variant. PostgreSQL locks serialize cart changes and checkout against
competing customers and normal admin/import stock edits. Quantity changes and
cart reads never extend a live hold. Expired holds stop counting automatically,
without requiring a background task. Removing an item releases its hold at once.
Customer bag reads refresh while open to show expired holds. Re-adding an expired
item creates a new reservation only if stock is still available.

Checkout is cash on delivery, using configured shipping and server-calculated
prices. A quote check rejects changed prices/shipping until the customer reviews
fresh totals. Orders snapshot descriptions, SKUs, quantities and prices, consume
stock transactionally, and clear the cart. A unique checkout key makes retries
idempotent. No online payment gateway or order email delivery is connected yet.

Customers can see their order history and cancel a placed order in the bag.
Staff with order change permission can move placed -> processing -> shipped ->
completed, or cancel before shipment. Cancellation restores stock exactly once.
Cart holds, order items and stock movements are read-only admin/export records;
orders are created only through checkout. All use ImportExportModelAdmin, with
unsafe imports/manual creates disabled. Product/variant stock adjustments create
inventory movement entries, and stale admin stock edits are rejected.

API: GET /api/shop/cart/, POST /api/shop/cart/items/ (absolute quantity; zero
removes), POST /api/shop/checkout/, GET /api/shop/orders/,
POST /api/shop/orders/<uuid>/cancel/. All customer writes use session auth + CSRF.
Cart and order ownership always come from the authenticated user.


Customer order references use a PostgreSQL sequence, displayed as ORD-YYYYMMDD-100001 (local order date plus an offset sequence).
Internal UUIDs remain unchanged for ownership-checked API operations. Reference
numbers are unique and permanent, with possible gaps after rolled-back checkouts.
Confirmation, history and details are separate bag views. Cancellation is offered
only in order details and requires an explicit Keep order / Yes, cancel order choice.


## Staff operations

React admin has dedicated Orders and Stock workspaces, advertised by the backend
only when registered ModelAdmin permissions allow access. Orders support search
by reference/customer/email/phone, status filters and counts, customer/delivery
information, permitted order item snapshots and confirmed fulfilment transitions.
Actions post through the existing Django admin form/save/audit adapter.

Stock lists simple products and individual variants (variant parents are excluded
from totals). It shows on-hand, unexpired cart reservations, available quantity,
tracking state and low-stock filters. Set the threshold in Site Settings. Adjust
stock using a signed quantity change and reason. The endpoint locks inventory,
checks the expected previous count, uses ModelAdmin forms/save hooks and retains
reservation and stale-write guards. Movements include the acting staff account,
reason and Django admin audit entry. Movement history requires its own view
permission. Child order item viewing requires the corresponding model permission.

Permissions are not granted automatically: configure staff Groups in Django admin.
No online payment collection, courier integration, refunds or automated alerts are
introduced by these operational workspaces.


Invoices are available from customer order confirmation/details and the staff
Orders workspace. The owner or a staff account with scoped order and order-item
view permission can open them. They use immutable order item/price snapshots and
current Site Settings branding, invoice address, phone and footer note. Print /
save PDF uses the browser print dialog and shared print stylesheet. COD invoices
show payable on delivery; a cancelled order is explicitly marked cancelled.


## Manual invoices

Orders -> Manual invoice lets permitted staff issue phone/counter invoices without
creating a customer account. It supports catalog products/variants at current
backend prices and custom descriptions with entered unit prices and per-unit
fixed discounts. Custom lines do not affect catalog stock. Shipping is entered
explicitly; payment terms remain cash on delivery/payable on delivery.

Grant Can create manual invoices, order change/view, order-item view, and the
relevant product/variant view permissions through Django admin. A server preview
calculates totals and validates every line. Issuing requires that exact reviewed
quote, uses a unique retry key, respects all cart holds, locks catalog inventory,
creates order/item snapshots and stock movements, and logs the issuing staff
member. Preview does not reserve or consume stock. Issued invoices appear in
Orders and can be printed from the same invoice page. Cancelling restores only
catalog-backed stock and never creates stock for custom items.


Manual invoice item rows expose discounts on the creation form, before review.
Catalog lines can inherit their catalog discount or use a fixed per-unit / percent
manual discount off the regular unit price. Custom lines support fixed/percent
discounts too. Manual discounts replace catalog discounts; they do not stack.
Django validates percentages, amounts and rounding, and invalidates the reviewed
quote when prices/discounts change. Review is read-only and includes total discount.


## Invoice amendments and history

Staff with Can amend invoices, order change/view and the relevant order-item /
catalog view permissions can open Edit invoice from order details. Customer,
address, notes, shipping, item descriptions/SKUs, items, quantities, regular prices
and discounts can be amended. References stay fixed, and company branding remains
in Site Settings. Every amendment requires a reason, a fresh server-calculated
review and the expected invoice version. An old form cannot overwrite newer edits
or status changes. Invoice and order detail reads lock the order while assembling
prices and items, avoiding mixed revisions.

Catalog quantity changes adjust inventory by the difference, preserving all live
cart holds. Preview rolls back temporary availability calculations; it never
changes committed stock. Cancelled invoices can be corrected without changing
inventory. Saving produces an immutable InvoiceRevision before/after snapshot,
actor, timestamp, reason, stock movements and Django admin audit record. Status
changes also produce a version/history entry. Grant Invoice revision view for the
history UI; revisions are registered with ImportExportModelAdmin but cannot be
manually added, imported, edited or deleted through either admin.

Catalog rows show the existing discount and current catalog selling price before
manual overrides. Staff order totals and review tables show regular prices,
discount amounts, discounted unit prices and net totals explicitly.


Payment state is separate from fulfillment. Staff need Can mark invoice paid or unpaid plus object-level Order change permission. Each change requires a reason and current revision; before/after values are recorded in Invoice revisions without altering stock. Paid/unpaid is displayed on printable invoices.

Set Delivery inside Dhaka and Delivery outside Dhaka in Site Settings. Checkout uses a selected delivery area and calculates the fee on the server; rate changes invalidate the checkout quote. Manual invoices and amendments offer the same two areas plus a custom charge. Existing orders retain their saved charges; migration initializes both area rates from the previous flat charge.


Payments and refunds are append-only OrderPayment records. Staff use Record payment / Record refund in order details with the existing payment permission and object-level Order change access. Amount, method, reference, effective date, staff actor and notes are preserved. Duplicate submission keys are idempotent and version checks reject stale submissions. Partial/full/unpaid status, net paid, amount due and refund due derive from the ledger; cancellation makes the refundable balance equal to net receipts. Invoice amendments never erase receipts. Refunds cannot exceed net receipts; new receipts cannot exceed the remaining balance. These controls record completed money movements and do not initiate transfers. Existing paid flags are migrated as explicitly labelled opening balances; original method and payment date are unknown.


Storefront checkout offers COD and an optional delivery-charge advance. Configure delivery_advance_enabled, instructions and a list of channels (bkash/nagad/bank) in Site Settings. No payment option transfers money through a gateway: advance checkout collects a transaction reference, keeps the order unpaid, and shows a pending-verification notice. Staff verify actual receipt through Record payment using the submitted channel/reference and snapshotted delivery amount. Only that ledger entry reduces the remaining balance.


Dummy payments can be enabled in Site Settings for gateway-free checkout demonstrations. Delivery advance simulates only the server-calculated delivery fee; Pay now simulates the complete order total. Simulation and order/stock writes are one transaction and checkout-key retries cannot duplicate receipts. Generated receipts use method dummy and is_simulated=true; confirmation, staff details and invoices show a simulation notice. No money is transferred. The default remains disabled on fresh installations.


Delivery locations are managed through City and Area in Django admin and the generated React controls. Area has a foreign key to City. Checkout and manual invoices show City first and filter Area by the chosen City. Django validates the pair and saves location foreign keys alongside historical city/area text on orders, preserving printed invoices when names change. Existing order locations populate the initial directory without changing their saved text. Required checkout fields display an asterisk; email, postal code and notes remain optional.


Checkout City/Area fields use database-backed accessible comboboxes. Search begins after one character with 200 ms debounce, cancellation of stale requests and at most 20 active results. Area search requires a City ID. Arrow keys, Enter, Escape and native required-field validation are supported; only a selected result is submitted.


Cart reservations default to 10 minutes and additions share the earliest active cart deadline. Checkout details auto-save to the authenticated cart, including canonical City/Area selections and payment choice. Draft APIs use session auth and CSRF, bind writes to the current expiry, never extend stock holds, and hide/clear expired drafts. Checkout and removing the last item clear the draft.


Invoice delivery/return clauses are editable in Site Settings under Invoice details: invoice_terms_heading and invoice_terms (one clause per line). The {site_name} placeholder resolves using current backend branding. Blank terms hide the block. Clauses sit left of totals on desktop/print and below totals on mobile.


Products now have one required Category and optional many-to-many curated Collections. The previous Rings/Necklaces/Earrings/Bracelets group table is renamed to Category without changing IDs or images; a fresh Collection directory supports cross-category edits such as Bridal or New Arrivals. Product forms expose both. Storefront browse/filter uses categories and an additional collection filter when curated collections exist. Category deactivation blocks sales; a deactivated collection only removes that curated grouping.

Every product and variant has a required SKU. New forms receive a generated PRD-/VAR- code which staff may replace. Migration fills only blank product codes, while existing invoice/order SKU snapshots stay unchanged. Case-insensitive SKU uniqueness spans products and variants, serialized by a PostgreSQL advisory lock during model saves; Django admin and import-export share the same model validation.
