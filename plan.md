# Gemini AI assistants plan

## Goal
Make product entry easy and help customers choose jewellery, with strict AI spending controls.

## 1. Admin product assistant
- In `/control/`, staff upload photos and enter the price; optional notes and stock are supported.
- Gemini analyses photos and proposes title, description, existing category, tags, optional collections, main image and gallery order.
- Default omitted stock to **1** for new products only. Preserve explicit **0**; never reset existing stock during edits or retries. Resolve variant quantities before saving.
- Suggest separate products or variants when appropriate; ask staff when image grouping is ambiguous.
- Generate globally unique SKUs through Django. Do not guess materials, plating, authenticity, measurements or durability claims from photos.
- Show an editable preview with unknown facts highlighted. Staff explicitly approve saving/publishing; AI cannot publish independently.
- Stage photos and generated content until approval. Use existing image conversion, validation and product-save rules.
- Make retries idempotent so repeated requests cannot create duplicate products.

## 2. Storefront fashion chatbot
- Mobile-friendly chat for occasion, outfit, colour preferences and budget.
- Optionally accept a dress or face photo for style suggestions; offer the same help without a photo.
- Recommend only relevant, published, purchasable catalog items. Return product cards with current Django prices, availability and links.
- Ground answers to product and store-policy questions in backend records; ask or state uncertainty when information is missing.
- Treat face-based advice as optional style suggestions; avoid identity, sensitive-trait or attractiveness judgments.
- Keep customer access read-only: no catalog edits, inventory changes or autonomous purchases.

## 3. Credit limits
Suggested initial settings, adjustable in backend SiteSettings:

| Control | Starting policy |
| --- | --- |
| Signed-in customer | 20 messages/day |
| Guest session | 10 messages/day |
| Burst limit | 3 messages/minute per customer/session |
| Image analysis | 2 uploads/day per customer/session |
| Upload size | 1 image/message, maximum 5 MB; resize before inference |
| Message length | Maximum 2,000 characters |
| Reply length | Maximum 300 output tokens |
| Context | Bounded recent conversation plus compact summary |
| Store budget | Required configurable daily cap before enabling public chat |

- Enforce limits server-side before Gemini calls using atomic shared counters. Add configurable IP abuse limits across guest sessions; trust forwarded IPs only from configured proxies.
- Separate admin and customer quotas. Reserve estimated spend before requests, reconcile actual usage, and enforce concurrency, timeout and retry limits.
- Calculate estimated spend using configured model prices; provider billing may differ. Check current Gemini pricing and available provider quota controls before launch.
- Retrieve a small relevant catalog shortlist instead of sending the whole catalog. Cache nonpersonal common answers; recheck price and availability before display.
- Avoid repeated analysis of the same image within its session. Do not share personal-photo caches across users.
- At a limit, stop paid calls and show backend-authored copy plus ordinary catalog browsing.

## 4. Implementation rules
- Use the existing `sanjilas` app, Django/PostgreSQL and React. No new Django app.
- Shared Gemini service in Django; API key stays in server environment configuration. Select a currently supported image-and-text model after a small quality/cost trial.
- Request structured output and validate it against allowed fields, catalog IDs and Django rules. Treat image text, supplier notes and customer prompts as untrusted input.
- Reuse ModelAdmin forms, permissions, hooks, validation and audit logging; retain session authentication and CSRF protection for writes.
- Register every new concrete model with import-export admin and expose controls through the existing registry-driven React admin.
- Keep labels/settings in the backend and all authored styling in `frontend/src/index.css`; support all existing themes and mobile layouts.
- Customer photos are temporary, explicitly disclosed as being sent to Gemini, and deleted after processing with cleanup for failures. Verify provider retention terms before launch; do not promise provider-side deletion without evidence.
- Keep usage logs free of raw photos, API keys and unnecessary personal content. Define chat retention before enabling persistence.

## 5. Delivery order
1. Inspect current catalog/admin flows; confirm Gemini model, budget and provider data terms.
2. Build the shared Gemini integration, structured validation, usage accounting and limits.
3. Build admin photo-to-product preview and approval flow.
4. Build catalog-grounded text chat, then optional outfit/face photo support.
5. Pilot on 20 products and representative customer conversations; tune limits before public rollout.

## Acceptance checks
- Photos + price produce an editable draft; omitted stock becomes 1 and explicit 0 remains 0.
- Image grouping, category assignment, variants and unique SKUs validate correctly; retries do not duplicate products.
- Unsupported material/quality claims are absent; unknown facts are flagged.
- Customers see valid catalog links and current prices/availability; no private/admin records are exposed.
- Concurrent requests cannot bypass quotas or budget reservations; provider failures do not trigger unbounded retries.
- Permissions, CSRF, image cleanup, mobile layouts and theme compatibility pass checks.
- Record product-entry time, staff corrections, recommendation relevance and estimated cost per completed interaction before expanding.

## Scope
Initial implementation is available locally: product photo-to-draft approval, storefront fashion chat, optional photo input and PostgreSQL-backed quotas/token accounting. See `docs/ai-assistants.md` for setup, verification and limitations. Live Gemini validation awaits the API key; no production deployment is included. Currency billing caps, common-answer caching, batch intake, templates and variant automation remain follow-up work.
