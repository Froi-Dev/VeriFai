# Verif.ai browser extension

Chrome Manifest V3 extension for the Verif.ai frontend and FastAPI backend. The popup, selection panels and screenshot cropper use the current Philippine brand palette and logo.

## Build and load

```sh
npm ci
npm test
npm run build
```

Open `chrome://extensions`, enable Developer mode, then load the `dist` directory unpacked. After rebuilding, reload the extension and refresh any existing webpages so their content scripts update.

## Backend connection

Configure `BACKEND_URL` and `DASHBOARD_URL` in `public/config.js`, then rebuild. Defaults are `http://localhost:8000` and `http://localhost:5173`. The popup and background worker share `public/api.js` so validation, authentication and response mapping stay consistent.

Start the existing Verif.ai backend normally. `/live` checks connectivity; it does not guarantee that every model or external evidence provider is ready.

- Signed-in text/news: `/api/v1/detector/text` (20–10,000 characters) and `/api/v1/news/verify` (5–10,000 characters). Scans never fall back to guest routes.
- Images: `/api/v1/detector/image` and `/api/v1/news/verify-image`, multipart field `image`. Both require sign-in.
- Sign in through the extension with an existing Verif.ai account, or use the dashboard's Connect extension button. Requests support HttpOnly session cookies and legacy bearer tokens; expired sessions attempt one refresh. If browser cookie policy prevents refresh, sign in again.

After a local build, run `python package.py` to update the website download ZIP.
The frontend Docker build does this automatically. Rebuild/recreate the frontend
container after extension changes to serve the new download; installed extensions
must also be updated/reloaded in the browser.

There are no simulated scan verdicts or offline heuristic fallbacks. Network, validation and authentication failures are shown as errors. Completed scans are saved locally; authenticated scans are also persisted by the backend. The frontend and extension do not automatically share browser storage or local scan history.

## Use

The extension popup contains only History and Dashboard, with History shown by default. All scans are explicitly user-triggered on the webpage: highlight text and click Analyze Text or Check News Validity, or press `Alt+Shift+F`, select an image region, and click Analyze. The cropper displays the finished result; scans also appear in History. Opening the popup does not start a scan. Browser-protected pages may restrict capture or content injection.

## Validation

`npm test` covers API contracts and worker flows, including slow text inference, unavailable services, auth refresh, percentage scales, image failures, and concurrent history writes. `npm run build` regenerates the loadable extension.

`npm run dev` starts Vite for popup styling; it does not emulate Chrome extension APIs or automatically reload an installed extension. Use `npm run build -- --watch` for repeated extension builds, and reload in Chrome after changes.
