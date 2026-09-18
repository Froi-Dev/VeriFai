# VeriFai Backend

FastAPI authentication, content-detection, and evidence-based news-verification API for the
existing PostgreSQL database.

## Text detector

`POST /api/v1/detector/text` runs the local XLM-RoBERTa classifier configured by
`TEXT_MODEL_PATH`. The route requires the same authenticated session as the dashboard,
accepts 20–10,000 characters, and returns AI/human probabilities plus a cautious verdict.
Long inputs are analyzed in overlapping 512-token windows instead of being silently cut off.

The configured `xlmr-ai-human-best` export declares `0=human` and `1=AI` in its
`id2label` metadata, so the detector resolves the class mapping directly from the model.

## Image detector

`POST /api/v1/detector/image` accepts one authenticated JPEG, PNG, WEBP, GIF, HEIC, or HEIF
image up to 10 MB. Gemini assesses visible generation/manipulation signals and returns a
structured classification, AI/authentic likelihoods, observed signals, and limitations. This
is a visual assessment rather than forensic proof; it does not claim to inspect unavailable
metadata or establish provenance.

## Fake News Analyzer

`POST /api/v1/news/verify` is separate from the AI-writing Text Analyzer. It accepts a text
claim. The primary engine searches live Google snippets through Serper, with
SearchAPI and Google Custom Search as provider fallbacks, and adjudicates the
retrieved evidence with `gemini-3.5-flash-lite`. It does not download HTML articles.
`NEWS_FAST_MODEL` can select `gemini-3.5-flash` instead. Text and image verification
share the Gemini key pool with OCR: round-robin selection skips rate-limited keys
for `GEMINI_KEY_COOLDOWN_SECONDS` (60 seconds by default).

The existing response schema and evidence groups are preserved. Citations must
match retrieved URLs, and successful empty searches return `UNVERIFIED` without
an LLM call. If search providers or Gemini attempts are exhausted, the original
deterministic verifier is used without another LLM adjudicator. That fallback:

- normalizes text while preserving names, dates, numbers, and negation;
- extracts entities, keywords, dates, and event categories with rules;
- searches configured national and regional Philippine outlets with several full-claim and
  altered-headline query views;
- searches VERA Files, Rappler Fact Check, and Tsek.ph first for an explicit assessment;
- uses Google Custom Search, SearchAPI, and Serper in configurable fallback order;
- deduplicates tracking URLs and copied headlines;
- pre-filters results before SSRF-protected article retrieval;
- combines entity/event overlap, TF-IDF cosine similarity, fuzzy matching, dates, source
  tiers, and explicit contradiction/debunk rules;
- returns grouped evidence, source URLs, a closest real story, and an explainable verdict.

No result is treated as `UNVERIFIED`, never as false. If all configured providers fail, the
response status is `SEARCH_UNAVAILABLE` and the verdict remains `UNVERIFIED`.

Configure at least one backend-only provider in `.env`. Google requires both
`GOOGLE_SEARCH_API_KEY` and `GOOGLE_CSE_ID`; the CSE browser widget is intentionally not used.
`NEWS_SEARCH_PROVIDER_ORDER`, `PHILIPPINE_NEWS_DOMAINS`, `TRUSTED_NEWS_DOMAINS`, thresholds,
scrape limits, and timeouts are all configurable. `PHILIPPINE_NEWS_DOMAINS` defines discovery
scope, while `TRUSTED_NEWS_DOMAINS` affects evidence weighting only. Do not place provider
credentials in Vite variables or frontend code.

Example authenticated request:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/news/verify `
  -ContentType application/json `
  -WebSession $session `
  -Body '{"text":"Ferdinand Marcos Jr. signed the Maharlika Investment Fund Act into law."}'
```

### Philippine news image fact-checking

`POST /api/v1/news/verify-image` accepts one authenticated JPEG, PNG, WEBP, GIF, HEIC, or
HEIF upload up to 10 MB. Pillow downsizes high-resolution sources before creating the bounded
OCR array; GIF and phone-native HEIF formats are normalized to JPEG for vision fallback.
Gemini Vision structured transcription is the primary OCR engine, using
`GEMINI_VISION_MODEL=gemini-3.5-flash-lite`. Headline blocks are joined into the
primary claim; body text is used when there is no headline. UI text, labels, and
watermarks are excluded from the claim. PaddleOCR remains an OCR failure fallback.

The response preserves `ocr.raw_text`, categorized blocks, the cleaned claim, OCR
provider and timing, and wraps the same complete verification response used by
the text route. Successful primary checks report zero scraped articles. Cold
PaddleOCR startup and deterministic fallback may take longer than the fast path.

Set `GEMINI_API_KEYS` to a comma-separated, backend-only key pool. The shared Gemini client
round-robins image detection and fallback OCR requests and temporarily skips credentials that
return quota, authentication, or permission errors. `GEMINI_API_KEY` remains supported for a
single-key deployment. Credentials are sent in the `x-goog-api-key` header and are never
exposed to the browser.
PaddleOCR is loaded lazily by default so each web process does not immediately allocate a copy.
`IMAGE_OCR_WARMUP=true` is available for a dedicated single-worker inference deployment. A
warmup failure is logged without taking unrelated API routes offline. Pre-cache the models in
deployments without model-host access.

Low-confidence OCR is never submitted for fact-checking unless the fallback returns a usable
transcription. Image provenance remains explicitly `UNKNOWN` because textual web search is not
a reverse-image search.

### Text detector deployment

The text model is loaded lazily by default (`TEXT_MODEL_WARMUP=false`). Run one asynchronous API
worker while the text and OCR models are in-process; each additional process would load another
copy of both model families. Scale the bounded I/O concurrency first, or deploy model inference
as a separately scaled service before increasing API process count. A single worker shares one
text model across up to `TEXT_MODEL_MAX_CONCURRENT_INFERENCES` bounded inference calls.

The model's `config.json` must identify the AI and human labels. For legacy models with generic
`LABEL_0`/`LABEL_1` metadata, set `TEXT_MODEL_AI_LABEL_ID` only after confirming the mapping from
the training pipeline. A model export containing `text_calibration.json` automatically uses its
held-out temperature and asymmetric review thresholds. Exports without that artifact present
scores as uncalibrated rather than inventing a real-world confidence claim.

The leakage-resistant fine-tuning, calibration, subgroup evaluation, dataset schema, and release
checklist are documented in [docs/text-detector-training.md](docs/text-detector-training.md).

Example authenticated upload:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/news/verify-image `
  -WebSession $session `
  -Form @{ image = Get-Item .\news-card.png }
```

## Reliability controls

- `GET /live` is process liveness and never depends on PostgreSQL. `GET /health` and
  `GET /api/v1/health` are readiness checks and return `503` when PostgreSQL is unavailable.
  Database unavailability no longer prevents application startup.
- Authentication for long-running detector and verification routes uses a short-lived database
  session, releasing its connection before model inference, searches, OCR, or scraping begins.
- `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, and `DATABASE_POOL_TIMEOUT_SECONDS` are explicit.
  Keep `instances * (pool size + overflow)` below the PostgreSQL connection budget after reserving
  capacity for migrations, administration, and monitoring.
- Search variants run concurrently behind `NEWS_MAX_CONCURRENT_SEARCH_REQUESTS`; article downloads
  reuse one keep-alive HTTP pool and are bounded by `NEWS_MAX_CONCURRENT_SCRAPES`. Image claims use
  the stricter `IMAGE_MAX_CONCURRENT_CLAIMS` limit.
- End-to-end deadlines cover text, news, and image analysis. Deadline expiry returns `504` and
  cancels outstanding asynchronous provider work.
- Successful results are cached by content hash. Development uses a bounded in-process TTL cache;
  production automatically reuses the Redis rate-limit URL unless `RESULT_CACHE_URL` is set.
  Simultaneous identical misses are coalesced to one computation.
- Every response carries `X-Request-ID`, and error bodies include the same support reference.
  `X-Cache` reports `HIT` or `MISS` for analysis routes.
- Evidence is ranked, publisher/copy-chain deduplicated, and capped by
  `NEWS_MAX_EVIDENCE_ITEMS`; weak related evidence has its own smaller cap.

## Security model

- Argon2id password hashing with per-password salts; legacy bcrypt hashes upgrade on login.
- Twelve-character password policy enforced independently by the API.
- 15-minute JWT access tokens in `HttpOnly` cookies.
- Opaque refresh tokens stored only as SHA-256 hashes and rotated on every refresh. A short,
  server-derived replay window makes simultaneous tab refreshes idempotent; delayed reuse still
  revokes the session.
- Server-side revocation plus idle and absolute expiry. User-Agent changes are audited and update
  the device metadata instead of invalidating a valid refresh token.
- Per-IP login throttling avoids attacker-triggered account lockout. Reaching the active-session
  limit rejects the new login explicitly instead of silently signing out an older device.
- Generic password-reset discovery responses, one-time reset tokens, and reset-driven global
  logout. A failed SMTP background delivery releases its idempotency key for retry.
- Password-reset requests return `503` for everyone when SMTP is not configured; production startup rejects missing SMTP settings instead of promising undeliverable mail.
- User/moderator/admin role dependencies; `/api/v1/admin/users` requires `admin`.
- Strict Pydantic request models, SQLAlchemy bound parameters, request-size limits, CORS allowlists, origin checks, security headers, and endpoint rate limits.
- Encrypted audit IP addresses when `DATA_ENCRYPTION_KEY` is configured; IP/user-agent session metadata is only stored as keyed fingerprints.

The frontend never receives or stores password hashes, salts, signing keys, refresh tokens, or access tokens in JavaScript. Browser authentication uses `Secure`, `HttpOnly`, `SameSite=Lax` cookies.

## Local setup

Use Python 3.11 or newer, copy `.env.example` to the ignored `.env`, and generate fresh secrets. Then:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
psql "$env:DATABASE_URL" -f migrations/001_security_hardening.sql
psql "$env:DATABASE_URL" -f migrations/002_auth_session_resilience.sql
uvicorn app.main:app --reload --port 8000
```

The first text request loads roughly 1.1 GB of model weights and can be slower than later
requests. `TEXT_MODEL_DEVICE=auto` uses CUDA when available and otherwise uses the CPU.

Example authenticated request:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/detector/text `
  -ContentType application/json `
  -WebSession $session `
  -Body '{"text":"A complete passage of at least twenty characters goes here."}'
```

Run checks with:

```powershell
ruff check .
pytest
```

For local development, route browser requests through the Vite same-origin proxy:

```env
VITE_API_URL=/api/v1
```

## Production requirements

- Terminate TLS at a trusted reverse proxy, use `sslmode=verify-full` (or at least `require`) for PostgreSQL, and set `ENVIRONMENT=production` and `COOKIE_SECURE=true`.
- Explicitly set `CORS_ORIGINS` and `TRUSTED_HOSTS`; wildcards are rejected.
- Store `JWT_SECRET`, `DATA_ENCRYPTION_KEY`, database credentials, Redis credentials, and SMTP credentials in the deployment secret manager—not source control or Vite variables.
- Set `RATE_LIMIT_STORAGE_URI` to Redis for consistent limits and shared result caching across
  instances. Set `RESULT_CACHE_URL` only when caching should use a separate Redis deployment.
- Apply migrations with an owner role, then run the API as a DML-only role using `002_least_privilege.example.sql` as a template.
- Configure encrypted database volumes/backups, restricted network access, rotation, and restore testing at the infrastructure layer.
- Serve the frontend with its own CSP, HSTS, `frame-ancestors 'none'`, and MIME-sniffing headers. API headers do not protect separately hosted HTML.

Password reset deliberately returns the same message for known and unknown accounts. Delivery requires SMTP configuration; reset tokens are never logged or stored in plaintext.
