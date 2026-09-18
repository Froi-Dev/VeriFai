const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");

function setup(connection, fetcher) {
  const state = { connection }; const listeners = {}; const calls = [];
  const chrome = {
    runtime: { id: "test-extension", onInstalled: { addListener: f => listeners.install = f }, onMessage: { addListener: f => listeners.message = f } },
    storage: { local: { setAccessLevel() {}, async get() { return state; }, async set(values) { Object.assign(state, values); } } },
    contextMenus: { onClicked: { addListener: f => listeners.click = f } },
    action: { async setBadgeText() {} },
    permissions: { async request() { return true; } },
  };
  vm.runInNewContext(readFileSync(__dirname + "/background.js", "utf8"), {
    chrome, URL, Date, Blob, FormData, AbortSignal,
    fetch: async (url, options) => { calls.push({ url, options }); return fetcher(url, options); },
  });
  return { state, listeners, calls };
}

test("guest selection uses shared token and guest endpoint", async () => {
  const env = setup({ mode: "guest", token: "shared-token" }, async () => ({ ok: true, json: async () => ({ classification: "Likely human-written" }) }));
  await env.listeners.click({ menuItemId: "text", selectionText: "This is a sufficiently long selected passage." });
  assert.equal(env.calls[0].url, "http://localhost:8000/api/v1/guest/detect-text");
  assert.equal(env.calls[0].options.headers["X-Guest-Token"], "shared-token");
  assert.equal(env.state.result.classification, "Likely human-written");
});
test("account fact check uses bearer and authenticated news endpoint", async () => {
  const env = setup({ mode: "account", token: "access", expiresAt: "2099-01-01" }, async () => ({ ok: true, json: async () => ({ verdict: "verified" }) }));
  await env.listeners.click({ menuItemId: "news", selectionText: "Some news claim" });
  assert.equal(env.calls[0].url, "http://localhost:8000/api/v1/news/verify");
  assert.equal(env.calls[0].options.headers.Authorization, "Bearer access");
});
test("quota rejection is displayed without retrying another endpoint", async () => {
  const env = setup({ mode: "guest", token: "shared" }, async () => ({ ok: false, status: 403, json: async () => ({ detail: { code: "QUOTA_EXCEEDED" } }) }));
  await env.listeners.click({ menuItemId: "news", selectionText: "Some news claim" });
  assert.match(env.state.result.error, /Naubos/);
  assert.equal(env.calls.length, 1);
});
test("untrusted pages cannot connect credentials", () => {
  const env = setup(undefined, () => { throw new Error("Must not fetch"); });
  env.listeners.message({ type: "connect", mode: "guest", token: "x" }, { id: "test-extension", tab: {}, frameId: 0, url: "https://attacker.example" }, () => { throw new Error("Must not reply"); });
  assert.equal(env.calls.length, 0);
  assert.equal(env.state.connection, undefined);
});
test("connection waits for backend validation", async () => {
  const env = setup(undefined, async () => ({ ok: true }));
  const reply = await new Promise(resolve => env.listeners.message({ type: "connect", mode: "guest", token: "shared" }, { id: "test-extension", tab: {}, frameId: 0, url: "http://localhost:5173/extension" }, resolve));
  assert.equal(reply.ok, true);
  assert.equal(env.state.connection.token, "shared");
});
test("image URL is downloaded client-side and uploaded to guest detector", async () => {
  const env = setup({ mode: "guest", token: "shared" }, async url => url === "https://example.com/image.png"
    ? new Response(new Uint8Array([137, 80, 78, 71]), { headers: { "Content-Type": "image/png" } })
    : { ok: true, json: async () => ({ classification: "Inconclusive" }) });
  await env.listeners.click({ menuItemId: "image", srcUrl: "https://example.com/image.png" });
  assert.equal(env.calls[1].url, "http://localhost:8000/api/v1/guest/detect-image");
  assert.ok(env.calls[1].options.body.get("image") instanceof Blob);
});
