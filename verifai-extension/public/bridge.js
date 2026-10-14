// Only injected on the two explicitly allowed local dashboard origins.
window.addEventListener("message", async event => {
  if (event.source !== window || event.origin !== location.origin) return;
  const data = event.data;
  if (data?.type !== "VERIFAI_CONNECT" || data.mode !== "account" ||
      typeof data.requestId !== "string" || typeof data.token !== "string" ||
      !data.token || data.token.length > 4096) return;
  let ok = false;
  try {
    const response = await chrome.runtime.sendMessage({
      type: "CONNECT_ACCOUNT", token: data.token, expiresAt: data.expiresAt,
    });
    ok = response?.ok === true;
  } catch { /* The dashboard displays reconnect instructions. */ }
  window.postMessage({ type: "VERIFAI_CONNECTED", requestId: data.requestId, ok }, location.origin);
});
