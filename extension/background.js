const API = "http://localhost:8000/api/v1";
const WEB_ORIGINS = new Set(["http://localhost:5173", "http://127.0.0.1:5173"]);
// Content scripts cannot read credentials back from storage.
chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "verifai", title: "Scan with VerifAI", contexts: ["selection", "image"] });
    chrome.contextMenus.create({ id: "text", parentId: "verifai", title: "AI Text Scanner", contexts: ["selection"] });
    chrome.contextMenus.create({ id: "news", parentId: "verifai", title: "Fake News / Fact Checker", contexts: ["selection"] });
    chrome.contextMenus.create({ id: "image", parentId: "verifai", title: "AI Image Scanner", contexts: ["image"] });
  });
});
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type !== "connect" || sender.id !== chrome.runtime.id || !sender.tab || sender.frameId !== 0) return;
  let origin;
  try { origin = new URL(sender.url).origin; } catch { return; }
  if (!WEB_ORIGINS.has(origin) || !["guest", "account"].includes(message.mode) || typeof message.token !== "string" || !message.token || message.token.length > 4096) return;
  const connection = { mode: message.mode, token: message.token, expiresAt: message.expiresAt };
  const headers = connection.mode === "guest" ? { "X-Guest-Token": connection.token } : { Authorization: `Bearer ${connection.token}` };
  fetch(API + (connection.mode === "guest" ? "/guest/quota" : "/auth/me"), { headers, credentials: "omit" })
    .then(async response => {
      if (!response.ok) throw new Error("Connection rejected");
      await chrome.storage.local.set({ connection });
      reply({ ok: true });
    }).catch(() => reply({ ok: false }));
  return true;
});

let scanning = false;
chrome.contextMenus.onClicked.addListener(async info => {
  const kind = info.menuItemId;
  if (!["text", "news", "image"].includes(kind) || scanning) return;
  scanning = true;
  try {
    // Permission request must originate directly from the context-menu gesture.
    if (kind === "image") {
      const url = new URL(info.srcUrl);
      if (!["https:", "http:"].includes(url.protocol)) throw new Error("Only HTTP(S) images are supported. Upload this image in the web app.");
      const granted = await chrome.permissions.request({ origins: [`${url.origin}/*`] });
      if (!granted) throw new Error("Image host permission was declined.");
    }
    const { connection } = await chrome.storage.local.get("connection");
    if (!connection) throw new Error("Open the VerifAI extension hub and connect your account or guest trial first.");
    if (connection.mode === "account" && Date.parse(connection.expiresAt) <= Date.now()) throw new Error("Session expired. Reconnect from the VerifAI extension hub.");
    await chrome.storage.local.set({ result: { status: "Scanning…", scanner: kind } });
    await chrome.action.setBadgeText({ text: "…" });
    const headers = connection.mode === "guest" ? { "X-Guest-Token": connection.token } : { Authorization: `Bearer ${connection.token}` };
    let body;
    if (kind === "image") {
      const image = await fetch(info.srcUrl, { credentials: "omit", signal: AbortSignal.timeout(20000) });
      if (!image.ok) throw new Error("Could not download image. Upload it in the web app.");
      if (Number(image.headers.get("content-length")) > 10485760) throw new Error("Image exceeds 10 MB.");
      const reader = image.body.getReader();
      const chunks = []; let total = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.length;
        if (total > 10485760) { await reader.cancel(); throw new Error("Image exceeds 10 MB."); }
        chunks.push(value);
      }
      const blob = new Blob(chunks, { type: image.headers.get("content-type")?.split(";")[0] || "application/octet-stream" });
      body = new FormData(); body.append("image", blob, "context-image");
    } else {
      const text = (info.selectionText || "").trim();
      if (text.length < (kind === "text" ? 20 : 5) || text.length > 10000) throw new Error("Select between " + (kind === "text" ? 20 : 5) + " and 10,000 characters.");
      headers["Content-Type"] = "application/json";
      body = JSON.stringify({ text });
    }
    const guestPaths = { text: "/guest/detect-text", image: "/guest/detect-image", news: "/guest/verify-news" };
    const accountPaths = { text: "/detector/text", image: "/detector/image", news: "/news/verify" };
    const response = await fetch(API + (connection.mode === "guest" ? guestPaths : accountPaths)[kind], { method: "POST", headers, body, credentials: "omit", signal: AbortSignal.timeout(180000) });
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 401) throw new Error("Session expired. Reconnect from the VerifAI extension hub.");
      if (result.detail?.code === "QUOTA_EXCEEDED") throw new Error("Naubos na ang libreng pagsubok. Gumawa ng libreng account sa VerifAI.");
      throw new Error(typeof result.detail === "string" ? result.detail : "Scan failed. Check your input and try again.");
    }
    await chrome.storage.local.set({ result: { scanner: kind, ...result } });
    await chrome.action.setBadgeText({ text: "✓" });
  } catch (error) {
    await chrome.storage.local.set({ result: { error: error.message } });
    await chrome.action.setBadgeText({ text: "!" });
  } finally { scanning = false; }
});
