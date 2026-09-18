# VerifAI guest trial and Chrome extension

## Run locally

1. Run the existing API on `http://localhost:8000` and Vite on port `5173`.
2. From `Verifai-backend`, run `.venv/Scripts/python.exe -m scripts.migrate_guest_quotas` (idempotent PostgreSQL migration). This migration has been applied to the configured development database during implementation.
3. Open `/guest/consent` for the trial, or sign in for account access.
4. Open `/extension`, download and extract the ZIP, and load its directory using **chrome://extensions → Developer mode → Load unpacked**.
5. Reload the web page after installation and select **Connect to Extension**. The popup reports the connection; right-click highlighted text or an HTTP(S) image for scanning. Results are available in the popup. Images require permission for their host and are uploaded as bounded files, never fetched by the API from arbitrary URLs.

Rebuild the downloadable artifact with `python extension/package.py`. The ZIP includes only the six runtime files, no secrets or dependencies. Run extension contract tests with `node --test extension/background.test.cjs`.

## Quota behavior

- The three guest scanner routes require a server-issued UUID via `X-Guest-Token` or the `verifai_guest` HttpOnly cookie. Consent creates a 30-day session; the web client also stores the token in localStorage for explicit extension connection.
- Limits are **3 text / 2 image / 1 news** in a rolling 24-hour window. Database write locks serialize reservations across workers. Cached results and requests that fail after reservation consume quota. Invalid credentials never invoke inference.
- Both the token's original HMAC(IP + User-Agent) identity and the current request identity must have remaining quota. Clearing cookies or changing the client-supplied canvas value does not reset IP/UA usage. The server stores hashed identifiers and a consent version, never raw IP or canvas data in these tables.
- Canvas is stored as consented corroborating metadata, not a trusted credential. Incognito/clearing storage alone cannot reset usage with the same IP/UA. Changing both network and browser identity can evade this heuristic; shared networks with identical User-Agents can share limits. This is not guaranteed unique-device identification.
- `403` returns `detail.code = QUOTA_EXCEEDED`, `detail.message = Quota Exceeded`, scanner and current quotas. Missing/expired sessions return `401`. Quota/status and token responses are `no-store`.
- Guest scans create no account scan history. Account scans retain their existing authentication and history behavior.

## Deployment

Set HTTPS and secure cookies using the backend's existing settings. Configure only trusted reverse proxies to supply client addresses; do not trust arbitrary forwarded headers. Keep the JWT/HMAC secret stable, as rotating it invalidates guest sessions and identity associations.

For production, replace the local API URL in `background.js` and `popup.js`, web origins in `background.js`, links in `popup.html`, and `host_permissions`/`content_scripts.matches` in `manifest.json` with your exact HTTPS deployments. Rebuild the ZIP and update the hub's development-only copy. Configure backend allowed origins and restrict extension-origin access to the installed production extension ID. The optional image-host permission is requested only for the selected image's origin.

Account connection tokens expire according to the existing access-token setting and remain subject to backend session revocation. Reconnect through the hub after expiry or auth-session rotation. Logging out/revoking the web session invalidates its extension token on the backend; the popup also supports local disconnection. No refresh tokens are exported.

Schedule retention maintenance: remove `guest_usage` rows older than 24 hours, expired `guest_sessions`, and `guest_identities` no longer referenced by either table. Expiry is enforced even before physical cleanup. Keep consented session metadata only for the 30-day session retention period.

## Validation

Backend coverage: rolling-window reset, token expiry, cookie reset resistance, network changes, simultaneous reservations, consent requirements and real guest route guards. Frontend: production TypeScript/Vite build. Extension: mocked Chrome API contract tests for guest/account routing, image uploads, quota errors and origin-restricted connection. Installing the unpacked extension and exercising Chrome's actual permission UI remains a manual browser check.
