/**
 * Verif.AI — Chrome Storage Helpers
 *
 * Thin wrappers around chrome.storage.local for type-safe,
 * promise-based access to extension state.
 */

// ─── Keys ───────────────────────────────────────────────────────────────────
const KEYS = {
  SCREENSHOT: "verifai_screenshot",
  CROPPED: "verifai_cropped",
  STATUS: "verifai_status",
  RESULTS: "verifai_results",
  CROP_MODE: "verifai_crop_mode",
  TEXT_HISTORY: "verifai_text_history",
  SCAN_HISTORY: "verifai_scan_history",
  LEGACY_TEXT_HISTORY: "factguard_text_history",
  LEGACY_STATUS: "factguard_status",
  LEGACY_RESULTS: "factguard_results",
  LEGACY_CROPPED: "factguard_cropped",
  LEGACY_SCREENSHOT: "factguard_screenshot",
};

// Maximum number of history entries to keep
const MAX_HISTORY = 60;

// ─── Screenshot ─────────────────────────────────────────────────────────────

/** Save the full-tab screenshot data URL. */
export async function saveScreenshot(dataUrl) {
  await chrome.storage.local.set({ [KEYS.SCREENSHOT]: dataUrl });
}

/** Retrieve the stored screenshot data URL. */
export async function getScreenshot() {
  const data = await chrome.storage.local.get([KEYS.SCREENSHOT, KEYS.LEGACY_SCREENSHOT]);
  return data[KEYS.SCREENSHOT] || data[KEYS.LEGACY_SCREENSHOT] || null;
}

// ─── Cropped Image ──────────────────────────────────────────────────────────

/** Save the cropped image data URL and optional mode. */
export async function saveCroppedImage(dataUrl, mode = "media") {
  await chrome.storage.local.set({ [KEYS.CROPPED]: dataUrl, [KEYS.CROP_MODE]: mode });
}

/** Retrieve the cropped image data URL. */
export async function getCroppedImage() {
  const data = await chrome.storage.local.get([KEYS.CROPPED, KEYS.LEGACY_CROPPED]);
  return data[KEYS.CROPPED] || data[KEYS.LEGACY_CROPPED] || null;
}

export async function getCropMode() {
  const data = await chrome.storage.local.get(KEYS.CROP_MODE);
  return data[KEYS.CROP_MODE] || "media";
}

// ─── Status ─────────────────────────────────────────────────────────────────
// Possible statuses: "idle" | "cropping" | "analyzing" | "done"

/** Set the current extension status. */
export async function setStatus(status) {
  await chrome.storage.local.set({ [KEYS.STATUS]: status });
}

/** Get the current extension status. */
export async function getStatus() {
  const data = await chrome.storage.local.get([KEYS.STATUS, KEYS.LEGACY_STATUS]);
  return data[KEYS.STATUS] || data[KEYS.LEGACY_STATUS] || "idle";
}

// ─── Results ────────────────────────────────────────────────────────────────

/** Save analysis results. */
export async function saveResults(results) {
  await chrome.storage.local.set({ [KEYS.RESULTS]: results });
}

/** Retrieve analysis results. */
export async function getResults() {
  const data = await chrome.storage.local.get([KEYS.RESULTS, KEYS.LEGACY_RESULTS]);
  return data[KEYS.RESULTS] || data[KEYS.LEGACY_RESULTS] || null;
}

// ─── Unified Scan History ───────────────────────────────────────────────────

/**
 * Retrieve unified scan history.
 * @returns {Promise<Array>} History entries, newest first.
 */
export async function getScanHistory() {
  const data = await chrome.storage.local.get([KEYS.SCAN_HISTORY, KEYS.TEXT_HISTORY, KEYS.LEGACY_TEXT_HISTORY]);
  if (data[KEYS.SCAN_HISTORY] && data[KEYS.SCAN_HISTORY].length > 0) {
    return data[KEYS.SCAN_HISTORY];
  }
  // Fallback to text history if unified history is empty
  const fallback = data[KEYS.TEXT_HISTORY] || data[KEYS.LEGACY_TEXT_HISTORY] || [];
  return fallback.map(item => ({
    ...item,
    kind: item.kind || "text",
  }));
}

/**
 * Save an analysis entry to unified scan history.
 * @param {Object} entry
 */
export async function saveScanHistory(entry) {
  try {
    const history = await getScanHistory();
    const newEntry = {
      id: entry.id || `VF-${Date.now().toString(36).toUpperCase()}`,
      kind: entry.kind || "text",
      title: entry.title || entry.snippet || "Scan",
      result: entry.result,
      timestamp: entry.timestamp || new Date().toISOString(),
    };

    history.unshift(newEntry);
    if (history.length > MAX_HISTORY) {
      history.length = MAX_HISTORY;
    }

    await chrome.storage.local.set({
      [KEYS.SCAN_HISTORY]: history,
      [KEYS.TEXT_HISTORY]: history.filter(h => h.kind === "text"),
    });
  } catch (err) {
    console.error("[VeriFai Storage] Failed to save scan history:", err);
  }
}

/**
 * Backward-compatible helper for text analysis history.
 */
export async function getTextHistory() {
  return getScanHistory();
}

/**
 * Backward-compatible saveTextAnalysis.
 */
export async function saveTextAnalysis(snippet, result) {
  return saveScanHistory({
    kind: "text",
    title: snippet,
    snippet: snippet.substring(0, 60),
    result: result,
  });
}

/**
 * Clear all scan history.
 */
export async function clearScanHistory() {
  await chrome.storage.local.remove([KEYS.SCAN_HISTORY, KEYS.TEXT_HISTORY, KEYS.LEGACY_TEXT_HISTORY]);
}

export async function clearTextHistory() {
  return clearScanHistory();
}

/** Clear only the image workflow while preserving history. */
export async function clearImageAnalysis() {
  await chrome.storage.local.remove([
    KEYS.SCREENSHOT,
    KEYS.CROPPED,
    KEYS.CROP_MODE,
    KEYS.LEGACY_SCREENSHOT,
    KEYS.LEGACY_CROPPED,
    KEYS.RESULTS,
    KEYS.LEGACY_RESULTS,
  ]);
  await setStatus("idle");
}

// ─── Clear All ──────────────────────────────────────────────────────────────

/** Reset all storage to initial state. */
export async function clearAll() {
  await chrome.storage.local.clear();
}
