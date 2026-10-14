/**
 * VeriFai — Extension API Client
 *
 * Connects the extension to the VeriFai Backend (http://localhost:8000/api/v1).
 * Uses authenticated endpoints with HttpOnly session cookies; legacy bearer tokens
 * remain supported. Installing the extension does not grant account access.
 */

import { BACKEND_URL } from "./config.js";
export { BACKEND_URL };
export const API_BASE = `${BACKEND_URL}/api/v1`;

const AUTH_STORAGE_KEY = "verifai_auth";

/**
 * Get stored auth credentials (token and user info)
 */
export async function getStoredAuth() {
  try {
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      const data = await chrome.storage.local.get(AUTH_STORAGE_KEY);
      return data[AUTH_STORAGE_KEY] || null;
    }
    const val = localStorage.getItem(AUTH_STORAGE_KEY);
    return val ? JSON.parse(val) : null;
  } catch {
    return null;
  }
}

/**
 * Save auth credentials
 */
export async function saveAuth(authData) {
  try {
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      await chrome.storage.local.set({ [AUTH_STORAGE_KEY]: authData });
    } else {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authData));
    }
  } catch (err) {
    console.error("[VeriFai API] Failed to save auth:", err);
  }
}

/**
 * Clear auth credentials
 */
export async function clearAuth() {
  try {
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      await chrome.storage.local.remove(AUTH_STORAGE_KEY);
    } else {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  } catch (err) {
    console.error("[VeriFai API] Failed to clear auth:", err);
  }
}

/**
 * Helper to build auth headers
 */
async function buildHeaders(customHeaders = {}, includeAuth = true) {
  const headers = { ...customHeaders };
  if (includeAuth) {
    const auth = await getStoredAuth();
    if (auth?.access_token) {
      headers["Authorization"] = `Bearer ${auth.access_token}`;
    }
  }
  return headers;
}

/**
 * Check backend liveness and readiness
 */
export async function checkBackendHealth() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const res = await apiFetch(`${BACKEND_URL}/live`, {
      method: "GET",
      signal: controller.signal,
    });
    return { ok: res.ok, status: res.status };
  } catch (err) {
    return { ok: false, error: err.message || "Cannot connect to VeriFai backend" };
  } finally { clearTimeout(timer); }
}

/**
 * Detect AI-generated text using XLM-RoBERTa
 *
 * @param {string} text
 * @returns {Promise<Object>}
 */
export async function detectText(text) {
  if (!text || typeof text !== "string" || text.trim().length < 20 || text.trim().length > 10000) {
    throw new Error("Select between 20 and 10,000 characters for AI writing detection.");
  }

  const endpoint = `${API_BASE}/detector/text`;
  const headers = await buildHeaders({ "Content-Type": "application/json" });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);

  try {
    const res = await apiFetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify({ text: text.trim() }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      const msg = res.status === 401 ? "Sign in to your VeriFai account in the extension or at http://localhost:5173, then retry." : errorDetail(errJson, "Text detection failed.");
      throw new Error(typeof msg === "string" ? msg : "Text detection failed.");
    }

    const data = await res.json();
    return {
      success: true,
      kind: "text",
      classification: data.classification,
      confidence: Math.round((data.confidence ?? 0) * 100),
      aiProbability: Math.round((data.ai_probability ?? 0) * 100),
      humanProbability: Math.round((data.human_probability ?? 0) * 100),
      signals: data.signals || [],
      scoreInterpretation: data.score_interpretation || "",
      chunksAnalyzed: data.chunks_analyzed || 1,
      inferenceTimeMs: Math.round(data.inference_time_ms || 0),
      cached: data.cached || false,
      modelName: data.model_name || "xlmr-ai-human-v4-enhanced",
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Verify Philippine news claims using evidence search pipeline
 *
 * @param {string} text
 * @returns {Promise<Object>}
 */
export async function verifyNews(text) {
  if (!text || typeof text !== "string" || text.trim().length < 5 || text.trim().length > 10000) {
    throw new Error("News claims must contain between 5 and 10,000 characters.");
  }

  const endpoint = `${API_BASE}/news/verify`;
  const headers = await buildHeaders({ "Content-Type": "application/json" });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);

  try {
    const res = await apiFetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify({ text: text.trim() }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      const msg = res.status === 404 ? "News verification is unavailable on this backend. Restart the updated Verif.ai backend." : res.status === 401 ? "Your session expired. Sign in again to verify news." : errorDetail(errJson, "News verification failed.");
      throw new Error(typeof msg === "string" ? msg : "News verification failed.");
    }

    const data = await res.json();
    return {
      success: true,
      kind: "news",
      verdict: data.verdict,
      status: data.status,
      confidence: data.confidence,
      explanation: data.explanation,
      contextWarnings: data.context_warnings || [],
      closestStory: data.closest_real_story || null,
      evidence: data.evidence || {},
      evidenceAnalysis: data.evidence_analysis || [],
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Convert base64 data URL to Blob
 */
export function dataUrlToBlob(dataUrl) {
  const parts = dataUrl.split(";base64,");
  const contentType = parts[0].split(":")[1] || "image/png";
  const raw = atob(parts[1]);
  const rawLength = raw.length;
  const uInt8Array = new Uint8Array(rawLength);
  for (let i = 0; i < rawLength; ++i) {
    uInt8Array[i] = raw.charCodeAt(i);
  }
  return new Blob([uInt8Array], { type: contentType });
}

/**
 * Detect AI image generation signals
 *
 * @param {string|Blob} imageInput - Base64 data URL or Blob
 * @returns {Promise<Object>}
 */
export async function detectImage(imageInput) {
  const blob = typeof imageInput === "string" ? dataUrlToBlob(imageInput) : imageInput;
  const formData = new FormData();
  formData.append("image", blob, "captured_region.png");

  const headers = await buildHeaders({}, true);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);

  try {
    const res = await apiFetch(`${API_BASE}/detector/image`, {
      method: "POST",
      headers,
      body: formData,
      signal: controller.signal,
    });

    if (!res.ok) {
      if (res.status === 401) {
        throw new Error("Sign in to your VeriFai account to run AI Image Forensics.");
      }
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errorDetail(errJson, "Image analysis failed."));
    }

    const data = await res.json();
    return {
      success: true,
      kind: "media",
      classification: data.classification,
      confidence: data.confidence,
      aiProbability: data.ai_probability,
      authenticProbability: data.authentic_probability,
      summary: data.summary,
      signals: data.signals || [],
      limitations: data.limitations || "",
      model: data.model || "Gemini Vision",
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Verify Philippine news image graphic via OCR & fact check
 *
 * @param {string|Blob} imageInput - Base64 data URL or Blob
 * @returns {Promise<Object>}
 */
export async function verifyNewsImage(imageInput) {
  const blob = typeof imageInput === "string" ? dataUrlToBlob(imageInput) : imageInput;
  const formData = new FormData();
  formData.append("image", blob, "news_graphic.png");

  const headers = await buildHeaders({}, true);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);

  try {
    const res = await apiFetch(`${API_BASE}/news/verify-image`, {
      method: "POST",
      headers,
      body: formData,
      signal: controller.signal,
    });

    if (!res.ok) {
      if (res.status === 401) {
        throw new Error("Sign in to your VeriFai account to run News Image Fact-Checking.");
      }
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errorDetail(errJson, "Image fact-checking failed."));
    }

    const data = await res.json();
    return {
      success: true,
      kind: "news_image",
      status: data.status,
      classification: data.classification,
      confidence: data.confidence,
      overallVerdict: data.overall_verdict,
      reasoningSummary: data.reasoning_summary || data.summary,
      extracted: data.extracted || {},
      ocr: data.ocr || {},
      closestStory: data.closest_real_story || null,
      claims: data.claims || [],
    };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Login user
 */
export async function loginUser(email, password) {
  const res = await apiFetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email.trim(), password }),
  });

  if (!res.ok) {
    const errJson = await res.json().catch(() => ({}));
    throw new Error(errorDetail(errJson, "Login failed"));
  }

  const data = await res.json();
  const authPayload = {
    user: data.user,
    access_token: data.access_token || null,
    savedAt: new Date().toISOString(),
  };
  await saveAuth(authPayload);
  return authPayload;
}

/**
 * Get current user session
 */
export async function getCurrentUser() {
  const auth = await getStoredAuth();

  try {
    const res = await apiFetch(`${API_BASE}/auth/me`, {
      method: "GET",
      headers: await buildHeaders(),
    });
    if (res.status === 401) {
      await clearAuth();
      return null;
    }
    if (!res.ok) return auth?.user || null;
    const user = await res.json();
    await saveAuth({ ...(await getStoredAuth()), user, savedAt: new Date().toISOString() });
    return user;
  } catch {
    return auth?.user || null;
  }
}

/**
 * Logout user
 */
export async function logoutUser() {
  try {
    await apiFetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: await buildHeaders(),
    });
  } finally {
    await clearAuth();
  }
}

export function errorDetail(data, fallback) {
  if (Array.isArray(data.detail)) return data.detail.map(item => item.msg || item.message || fallback).join("; ");
  return typeof data.detail === "string" ? data.detail : fallback;
}

let refreshInFlight = null;
async function apiFetch(url, options = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 125000);
  // Extension API activity keeps a pending scan alive in the MV3 worker.
  const keepAlive = setInterval(() => globalThis.chrome?.runtime?.getPlatformInfo?.().catch(() => {}), 20000);
  try {
    const init = { ...options, credentials: "include", signal: controller.signal };
    let response = await fetch(url, init);
    if (response.status === 401 && !/\/auth\/(login|refresh|logout)$/.test(url)) {
      refreshInFlight ??= (async () => {
        const refreshed = await fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include", signal: AbortSignal.timeout(10000) });
        if (!refreshed.ok) {
          if (refreshed.status === 401) await clearAuth();
          return null;
        }
        const auth = await refreshed.json();
        await saveAuth(auth);
        return auth;
      })().finally(() => { refreshInFlight = null; });
      const auth = await refreshInFlight;
      if (auth) {
        const headers = new Headers(init.headers);
        headers.delete("Authorization");
        if (auth.access_token) headers.set("Authorization", `Bearer ${auth.access_token}`);
        response = await fetch(url, { ...init, headers: Object.fromEntries(headers.entries()) });
      }
    }
    return response;
  } catch (err) {
    if (err.name === "AbortError" || err.name === "TimeoutError") throw new Error("The scan timed out. Please try again.");
    if (err instanceof TypeError) throw new Error(`Cannot reach VeriFai at ${BACKEND_URL}. Check that the backend is running, then retry.`);
    throw err;
  } finally {
    clearTimeout(timer);
    clearInterval(keepAlive);
    options.signal?.removeEventListener("abort", abort);
  }
}
