# Gemini assistants

## Local setup
1. Add `GEMINI_API_KEY=...` to `ecom/.env`. Keep it out of Git and the frontend.
2. Optional: set `GEMINI_MODEL=gemini-3.5-flash-lite`; this is the default. Site Settings can override it.
3. Run `venv\Scripts\python.exe ecom/manage.py migrate` and restart Django. Run the storefront using the existing frontend commands/build process.
4. Open `/control/#/assistant`, or use **Create product with AI** on the control dashboard.
5. To test customer chat, enable **AI chat enabled** in Site Settings. It starts disabled.

## Product intake
- Upload one to four photos of one product, enter price, optionally stock and confirmed facts.
- AI proposes copy, an existing category, existing tags/collections and cover/gallery order. It flags unknown facts; ambiguous product/variant groups require clarification rather than automatic creation.
- Review/edit the draft, move photos earlier/later, and explicitly approve saving. Check **Publish on storefront** to publish; otherwise the new product stays inactive.
- Blank stock means one piece; explicit zero remains zero. Django generates the SKU.
- Images remain in the browser/request until approval; final files use the existing WebP conversion pipeline. Drafts expire after two hours; save retries return the same product.
- The first version does not create variants, categories or tags automatically. After saving, related catalog controls remain available through the normal product editor.

## Customer chat
- Offers occasion/outfit/budget advice and optional dress/face-photo style suggestions.
- Product cards use current catalog prices and purchasable availability, rechecked after inference. The assistant cannot write catalog, account or order data.
- Retrieval uses a bounded text-ranked catalog shortlist, not every product. Evaluate recommendation quality with the real catalog, especially image-only style requests.
- A photo requires explicit consent. It is resized, stripped of metadata for inference and sent inline to Gemini, with no stored store-side photo record. Normal request temporary files are closed after processing.
- The last four message/reply pairs are retained in the Django session; at most two shortened pairs are sent as context. Session retention follows the existing Django session policy. Do not send unnecessary personal information.
- Google's provider-side use/retention depends on the API account and service terms; verify these before public launch.

## Limits and accounting
Site Settings controls customer/guest daily messages, daily customer image uploads, burst limits, guest IP abuse limits, admin daily requests, combined store daily requests and combined reserved-token budget. Zero disables the corresponding allowance. Defaults are 20 customer messages/day, 10 guest messages/day, 2 customer images/day, 3 requests/minute, 40 public requests/IP/day, 50 admin requests/day, 100 combined requests/day and 200,000 reserved tokens/day.

PostgreSQL row locks serialize reservations across workers. An identity can have one model request in flight (45-second lease); Gemini HTTP operations have a 30-second socket timeout and no automatic retries. Guest sessions are established by the config endpoint; IP limits also apply if guests change sessions. Only configured proxy peers may supply forwarded IPs.

Before inference, a conservative token allowance is reserved. On a response containing usage metadata it is reconciled to actual total tokens, including thinking. Failed/unknown-usage attempts retain their reservation and consume request quota. The daily token budget is **not a currency billing cap**; model rates determine actual charges. Provider quotas/billing controls should also be configured. Neither assistant uses paid search tools or autonomous agent loops.

Usage counters and product drafts have read-only, permission-checked Django and React admin controls. API keys, prompts, photo bytes and provider error bodies are not written into these usage records.

Run `venv\Scripts\python.exe ecom/manage.py purge_ai_data` daily through existing server maintenance to clear expired draft payloads and old counters. Continue the normal Django `clearsessions` maintenance for expired session data. No maintenance schedule is installed by this change.

## Verification
Run `venv\Scripts\python.exe ecom/manage.py test sanjilas.test_ai sanjilas.test_control --keepdb --noinput`, plus `npm run lint` and `npm run build` in `frontend/`.

Tests mock Gemini, including transport payloads, failures and usage accounting; they do not validate live Gemini output quality or account eligibility. Test real photos and multilingual conversations after adding the key. Review Google's current API documentation when changing model families; older Gemini models use different thinking settings.

## Later work
Batch intake, variant creation, duplicate-product suggestions, reusable product templates, common-answer caching and richer semantic catalog retrieval remain follow-up improvements.

## Provider references
- [Image understanding](https://ai.google.dev/gemini-api/docs/image-understanding)
- [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Generate Content API](https://ai.google.dev/api/generate-content)
- [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
