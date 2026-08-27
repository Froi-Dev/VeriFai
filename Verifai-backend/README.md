# VeriFai Backend

FastAPI authentication, content-detection, and evidence-based news-verification API for the
existing PostgreSQL database.

## Text detector

`POST /api/v1/detector/text` runs the local XLM-RoBERTa classifier configured by
`TEXT_MODEL_PATH`. The route requires the same authenticated session as the dashboard,
accepts 20–10,000 characters, and returns AI/human probabilities plus a cautious verdict.
Long inputs are analyzed in overlapping 512-token windows instead of being silently cut off.

The supplied model export has two labels but no `id2label` metadata. The default assumes
the training convention `0=human` and `1=AI`. Set `TEXT_MODEL_AI_LABEL_ID=0` if the training
dataset used the reverse mapping.

## Fake News Analyzer

`POST /api/v1/news/verify` is separate from the AI-writing Text Analyzer. It accepts a text
claim and never sends that claim to an AI model. The deterministic pipeline:

- normalizes text while preserving names, dates, numbers, and negation;
- extracts entities, keywords, dates, and event categories with rules;
- searches configured national and regional Philippine outlets with several full-claim and
  altered-headline query views;
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

## Security model

- Argon2id password hashing with per-password salts; legacy bcrypt hashes upgrade on login.
- Twelve-character password policy enforced independently by the API.
- 15-minute JWT access tokens in `HttpOnly` cookies.
- Opaque refresh tokens stored only as SHA-256 hashes, rotated on every refresh.
- Server-side revocation, idle/absolute expiry, client fingerprint checks, and reuse detection.
- Account lockout, generic password-reset discovery responses, one-time reset tokens, and reset-driven global logout.
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

Set the frontend's public API location in its `.env`:

```env
VITE_API_URL=http://localhost:8000/api/v1
```

## Production requirements

- Terminate TLS at a trusted reverse proxy, use `sslmode=verify-full` (or at least `require`) for PostgreSQL, and set `ENVIRONMENT=production` and `COOKIE_SECURE=true`.
- Explicitly set `CORS_ORIGINS` and `TRUSTED_HOSTS`; wildcards are rejected.
- Store `JWT_SECRET`, `DATA_ENCRYPTION_KEY`, database credentials, Redis credentials, and SMTP credentials in the deployment secret manager—not source control or Vite variables.
- Set `RATE_LIMIT_STORAGE_URI` to Redis for consistent limits across workers.
- Apply migrations with an owner role, then run the API as a DML-only role using `002_least_privilege.example.sql` as a template.
- Configure encrypted database volumes/backups, restricted network access, rotation, and restore testing at the infrastructure layer.
- Serve the frontend with its own CSP, HSTS, `frame-ancestors 'none'`, and MIME-sniffing headers. API headers do not protect separately hosted HTML.

Password reset deliberately returns the same message for known and unknown accounts. Delivery requires SMTP configuration; reset tokens are never logged or stored in plaintext.
