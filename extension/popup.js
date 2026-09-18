function render(value) {
  if (value && typeof value === "object") {
    const list = document.createElement("dl");
    for (const [key, item] of Object.entries(value)) {
      const title = document.createElement("dt"); title.textContent = key.replaceAll("_", " ");
      const detail = document.createElement("dd"); detail.append(render(item)); list.append(title, detail);
    }
    return list;
  }
  const node = document.createElement("span"); node.textContent = String(value ?? ""); return node;
}
async function refresh() {
  const { connection, result } = await chrome.storage.local.get(["connection", "result"]);
  document.querySelector("#connection").textContent = connection ? `Connected: ${connection.mode}` : "Not connected";
  document.querySelector("#result").replaceChildren(render(result || "No scans yet."));
  document.querySelector("#quota").textContent = "";
  if (connection?.mode === "guest") {
    try {
      const response = await fetch("http://localhost:8000/api/v1/guest/quota", { headers: { "X-Guest-Token": connection.token }, credentials: "omit" });
      if (!response.ok) throw new Error();
      const { quotas } = await response.json();
      document.querySelector("#quota").textContent = Object.entries(quotas).map(([key, q]) => `${key}: ${q.remaining}/${q.limit}`).join(" · ");
    } catch { document.querySelector("#quota").textContent = "Quota unavailable. Reconnect or check the backend."; }
  }
}
document.querySelector("#disconnect").addEventListener("click", async () => {
  await chrome.storage.local.remove(["connection", "result"]);
  await chrome.action.setBadgeText({ text: "" });
});
chrome.storage.onChanged.addListener(refresh);
refresh();
