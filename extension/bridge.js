// This script runs only on explicitly allowlisted VerifAI web origins.
window.addEventListener("message", async event => {
  if (event.source !== window || event.origin !== location.origin) return;
  const data = event.data;
  if (data?.type !== "VERIFAI_CONNECT" || typeof data.requestId !== "string") return;
  if (!["guest", "account"].includes(data.mode) || typeof data.token !== "string" || data.token.length > 4096) return;
  let ok = false;
  try {
    const response = await chrome.runtime.sendMessage({ type: "connect", mode: data.mode, token: data.token, expiresAt: data.expiresAt });
    ok = response?.ok === true;
  } catch { /* Popup offers reload/reconnect instructions. */ }
  window.postMessage({ type: "VERIFAI_CONNECTED", requestId: data.requestId, ok }, location.origin);
});
