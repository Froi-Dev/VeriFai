/**
 * VeriFai — Background Service Worker
 *
 * Responsibilities:
 * 1. Listen for the Alt+Shift+F keyboard command or popup action
 * 2. Capture the visible tab as a screenshot
 * 3. Open the cropper window and receive cropped image
 * 4. Dispatch live AI detection & Fact-Checking requests to the VeriFai Backend (http://localhost:8000)
 * 5. Handle ANALYZE_TEXT and VERIFY_NEWS from content script and popup
 * 6. Save scan results to history in chrome.storage.local
 */

import { detectText, verifyNews, detectImage, verifyNewsImage, checkBackendHealth, saveAuth, API_BASE } from "./api.js";

const KEYS = {
  SCREENSHOT: "verifai_screenshot",
  CROPPED: "verifai_cropped",
  STATUS: "verifai_status",
  RESULTS: "verifai_results",
  CROP_MODE: "verifai_crop_mode",
  SCAN_HISTORY: "verifai_scan_history",
  AUTH: "verifai_auth",
  // Legacy keys for backward compatibility
  LEGACY_SCREENSHOT: "factguard_screenshot",
  LEGACY_CROPPED: "factguard_cropped",
  LEGACY_STATUS: "factguard_status",
  LEGACY_RESULTS: "factguard_results",
  LEGACY_TEXT_HISTORY: "factguard_text_history",
};

const MAX_HISTORY = 60;

// ─── Image Capture ───────────────────────────────────────────────────────────
async function startImageCapture(mode = "media") {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    throw new Error("No active browser tab was found.");
  }

  const screenshotDataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: "png",
    quality: 100,
  });

  await chrome.storage.local.set({
    [KEYS.SCREENSHOT]: screenshotDataUrl,
    [KEYS.LEGACY_SCREENSHOT]: screenshotDataUrl,
    [KEYS.STATUS]: "cropping",
    [KEYS.LEGACY_STATUS]: "cropping",
    [KEYS.RESULTS]: null,
    [KEYS.LEGACY_RESULTS]: null,
    [KEYS.CROPPED]: null,
    [KEYS.LEGACY_CROPPED]: null,
    [KEYS.CROP_MODE]: mode,
  });

  const screenWidth = tab.width || 1280;
  const screenHeight = tab.height || 720;
  const cropperWidth = Math.min(980, screenWidth);
  const cropperHeight = Math.min(720, screenHeight);

  await chrome.windows.create({
    url: chrome.runtime.getURL("cropper.html"),
    type: "popup",
    width: cropperWidth,
    height: cropperHeight,
    left: Math.max(0, Math.round((screenWidth - cropperWidth) / 2)),
    top: Math.max(0, Math.round((screenHeight - cropperHeight) / 2)),
    focused: true,
  });

  console.log("[VeriFai] Screenshot captured. Cropper opened with mode:", mode);
  return { ok: true };
}

// Keyboard shortcut listener (Alt+Shift+F)
chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "capture-screenshot") return;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) {
      await startImageCapture("media");
      return;
    }

    // Try capturing visible tab
    const screenshotDataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
      format: "png",
      quality: 100,
    });

    // Send message to in-page content script to launch in-page snipper
    try {
      await chrome.tabs.sendMessage(tab.id, {
        type: "TRIGGER_IMAGE_SNIP",
        screenshot: screenshotDataUrl,
        mode: "media",
      }, { frameId: 0 });
    } catch {
      // Content script may not be loaded yet, inject it dynamically
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["content/content.js"],
        });
        await chrome.scripting.insertCSS({
          target: { tabId: tab.id },
          files: ["content/content.css"],
        });
        await chrome.tabs.sendMessage(tab.id, {
          type: "TRIGGER_IMAGE_SNIP",
          screenshot: screenshotDataUrl,
          mode: "media",
        }, { frameId: 0 });
      } catch {
        // Fallback to cropper window if in-page injection is disallowed (e.g. chrome://)
        await startImageCapture("media");
      }
    }
  } catch (err) {
    console.error("[VeriFai] Shortcut screenshot capture failed:", err);
    await chrome.storage.local.set({ [KEYS.STATUS]: "idle", [KEYS.LEGACY_STATUS]: "idle" });
  }
});

// ─── Message Listener ────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "CONNECT_ACCOUNT") {
    let origin;
    try { origin = new URL(sender.url).origin; } catch { return false; }
    if (sender.id !== chrome.runtime.id || !sender.tab || sender.frameId !== 0 ||
        !["http://localhost:5173", "http://127.0.0.1:5173"].includes(origin) ||
        typeof message.token !== "string" || !message.token || message.token.length > 4096) return false;
    (async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/me`, {
          headers: { Authorization: `Bearer ${message.token}` },
          credentials: "omit", signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) throw new Error("Account connection rejected");
        await saveAuth({ user: await response.json(), access_token: message.token, expiresAt: message.expiresAt });
        sendResponse({ ok: true });
      } catch { sendResponse({ ok: false }); }
    })();
    return true;
  }
  // ── Request tab screenshot for in-page snipper ──
  if (message.type === "REQUEST_TAB_SCREENSHOT") {
    (async () => {
      try {
        const tab = sender.tab || (await chrome.tabs.query({ active: true, currentWindow: true }))[0];
        if (!tab) throw new Error("No active tab found");
        const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, {
          format: "png",
          quality: 100,
        });
        sendResponse({ ok: true, screenshot });
      } catch (err) {
        console.error("[VeriFai] Tab screenshot failed:", err);
        sendResponse({ ok: false, error: err.message || "Failed to capture tab" });
      }
    })();
    return true;
  }

  // ── Analyze image directly (from in-page snip) ──
  if (message.type === "ANALYZE_IMAGE") {
    handleCropComplete(message.croppedImage, message.mode || "media")
      .then((results) => sendResponse(results))
      .catch((err) => {
        console.error("[VeriFai] Image analysis error:", err);
        sendResponse({ error: err.message || "Image analysis failed" });
      });
    return true;
  }

  // ── Start image capture (fallback or manual) ──
  if (message.type === "START_IMAGE_CAPTURE") {
    startImageCapture(message.mode || "media")
      .then(sendResponse)
      .catch(async (err) => {
        console.error("[VeriFai] Screenshot capture failed:", err);
        await chrome.storage.local.set({ [KEYS.STATUS]: "idle", [KEYS.LEGACY_STATUS]: "idle" });
        sendResponse({ ok: false, error: err.message || "Screenshot capture failed." });
      });
    return true;
  }

  // ── Cropper: crop complete ──
  if (message.type === "CROP_COMPLETE") {
    handleCropComplete(message.croppedImage, message.mode || "media")
      .then((results) => sendResponse({ status: "received", results }))
      .catch((err) => sendResponse({ error: err.message }));
    return true;
  }

  // ── Cropper: crop cancelled ──
  if (message.type === "CROP_CANCELLED") {
    chrome.storage.local.set({ [KEYS.STATUS]: "idle", [KEYS.LEGACY_STATUS]: "idle" });
    sendResponse({ status: "cancelled" });
    return true;
  }

  // ── Text AI Detection ──
  if (message.type === "ANALYZE_TEXT") {
    handleAnalyzeText(message.text)
      .then((result) => sendResponse(result))
      .catch((err) => {
        console.error("[VeriFai] Text analysis failed:", err);
        sendResponse({ error: err.message || "Analysis failed" });
      });
    return true;
  }

  // ── News Fact-Check ──
  if (message.type === "VERIFY_NEWS") {
    handleVerifyNews(message.text)
      .then((result) => sendResponse(result))
      .catch((err) => {
        console.error("[VeriFai] News verification failed:", err);
        sendResponse({ error: err.message || "Verification failed" });
      });
    return true;
  }

  // ── Check backend health ──
  if (message.type === "CHECK_BACKEND_HEALTH") {
    checkHealth()
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  return false;
});

const checkHealth = checkBackendHealth;

async function handleCropComplete(croppedImageDataUrl, mode = "media") {
  await chrome.storage.local.set({ [KEYS.CROPPED]: croppedImageDataUrl, [KEYS.STATUS]: "analyzing", [KEYS.RESULTS]: null, [KEYS.CROP_MODE]: mode });
  let result;
  try {
    result = mode === "news_image" ? await verifyNewsImage(croppedImageDataUrl) : await detectImage(croppedImageDataUrl);
    result.label = result.classification || result.overallVerdict;
    result.isAIGenerated = result.classification === "Likely AI-generated";
    result.details = { model: result.model || "VeriFai News Image Verification", timestamp: new Date().toISOString() };
    await saveToScanHistory({ kind: mode, title: mode === "news_image" ? "News Graphic Fact-Check" : "Image Visual AI Inspection", result });
  } catch (err) {
    result = { success: false, error: err.message, summary: err.message, kind: mode, label: "Analysis incomplete" };
  }
  await chrome.storage.local.set({ [KEYS.RESULTS]: result, [KEYS.STATUS]: result.error ? "error" : "done" });
  return result;
}

async function handleAnalyzeText(text) {
  const result = await detectText(text);
  result.label = result.classification;
  result.details = { model: result.modelName, timestamp: new Date().toISOString() };
  await saveToScanHistory({ kind: "text", title: text.substring(0, 70), result });
  return result;
}

async function handleVerifyNews(text) {
  const result = await verifyNews(text);
  result.label = result.verdict;
  result.details = { model: "VeriFai Philippine Fact-Check", timestamp: new Date().toISOString() };
  await saveToScanHistory({ kind: "news", title: text.substring(0, 70), result });
  return result;
}

// ─── Save to Scan History Helper ────────────────────────────────────────────
let historyQueue = Promise.resolve();
function saveToScanHistory(entry) {
  historyQueue = historyQueue.then(() => persistHistory(entry));
  return historyQueue;
}
async function persistHistory(entry) {
  try {
    const data = await chrome.storage.local.get([KEYS.SCAN_HISTORY, KEYS.LEGACY_TEXT_HISTORY]);
    const history = data[KEYS.SCAN_HISTORY] || data[KEYS.LEGACY_TEXT_HISTORY] || [];

    const newEntry = {
      id: `VF-${crypto.randomUUID()}`,
      kind: entry.kind || "text",
      title: entry.title || "Scan",
      snippet: entry.title || "Scan",
      result: entry.result,
      timestamp: new Date().toISOString(),
    };

    history.unshift(newEntry);
    if (history.length > MAX_HISTORY) {
      history.length = MAX_HISTORY;
    }

    await chrome.storage.local.set({
      [KEYS.SCAN_HISTORY]: history,
      [KEYS.LEGACY_TEXT_HISTORY]: history,
    });
  } catch (err) {
    console.error("[VeriFai] Failed to save history:", err);
  }
}
