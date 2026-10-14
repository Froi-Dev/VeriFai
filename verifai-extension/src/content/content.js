/**
 * VeriFai — In-Page Content Script (Vanilla JS)
 *
 * Theme: VeriFai Stark Paper/Ink with Crimson Accent & Official Brand Mark.
 * Default: White/Light mode with Dark Mode Toggleable.
 * Trigger Buttons:
 *   - "Analyze Text" (Primary Crimson)
 *   - "Check News Validity" (Secondary Stark Outline)
 */

(function () {
  "use strict";

  if (window.__verifaiContentInjected) return;
  window.__verifaiContentInjected = true;

  const MIN_SELECTION_LENGTH = 5;
  const DEBOUNCE_MS = 140;
  const BTN_ID = "verifai-trigger-btn";
  const TOOLTIP_ID = "verifai-tooltip";
  const LOADER_ID = "verifai-inpage-loader";
  const MODAL_ID = "verifai-image-result-modal";
  const SNIP_OVERLAY_ID = "verifai-snip-overlay";
  const SNIP_TOOLBAR_ID = "verifai-snip-toolbar";

  let triggerBtn = null;
  let tooltip = null;
  let imageResultModal = null;
  let inpageLoader = null;
  let snipOverlay = null;

  let isAnalyzingText = false;
  let savedSelectionText = "";
  let savedSelectionRect = null;
  let debounceTimer = null;

  // Dark Mode preference: synced with storage or localStorage
  let isDarkMode = false;
  try {
    const saved = localStorage.getItem("verifai_inpage_dark");
    if (saved !== null) {
      isDarkMode = saved === "true";
    }
  } catch {
    isDarkMode = false;
  }

  // ─── VeriFai Official Emblem & SVGs ─────────────────────────────────────────
  const BRAND_EMBLEM_HTML = `<svg class="verifai-brand-symbol" width="24" height="24" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" fill="none" aria-hidden="true">
      <path
        d="M5 25V11a6 6 0 0 1 6-6h15M5 56v13a6 6 0 0 0 6 6h15"
        stroke="#0B3D91"
        stroke-width="5"
      />
      <path
        d="M54 5h15a6 6 0 0 1 6 6v14M75 56v13a6 6 0 0 1-6 6H54"
        stroke="#D7263D"
        stroke-width="5"
      />
      <path d="m16 26 24 35 24-35H51L40 42 29 26H16Z" fill="#0b3d91" />
      <path
        d="m40 10 2.5 4-1 13L40 30l-1.5-3-1-13 2.5-4Zm-13 7 4 1 7 12-3-1-9-9 1-3Zm26 0-4 1-7 12 3-1 9-9-1-3ZM33 13l3 2 3 14-2-2-5-12 1-2Zm14 0-3 2-3 14 2-2 5-12-1-2Z"
        fill="#F4B400"
      />
      <path
        d="m17 43 1.3 3.8h4l-3.2 2.4 1.2 3.8-3.3-2.4-3.3 2.4 1.3-3.8-3.3-2.4h4L17 43Zm46 0 1.3 3.8h4l-3.2 2.4 1.2 3.8-3.3-2.4-3.3 2.4 1.3-3.8-3.3-2.4h4L63 43ZM40 64l1.3 3.8h4l-3.2 2.4 1.2 3.8-3.3-2.4-3.3 2.4 1.3-3.8-3.3-2.4h4L40 64Z"
        fill="#F4B400"
      />
    </svg>`;

  const SUN_SVG = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
  const MOON_SVG = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
  const SPARK_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3m0 12v3M3 12h3m12 0h3m-2.6-6.4l-2.1 2.1M5.6 18.4l-2.1 2.1m14.9 0l-2.1-2.1M5.6 5.6L3.5 7.7"/></svg>`;
  const NEWSPAPER_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg>`;
  const CHECK_SVG = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
  const ALERT_SVG = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
  const CROP_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6.13 1L6 16a2 2 0 0 0 2 2h15"/><path d="M1 6.13L16 6a2 2 0 0 1 2 2v15"/></svg>`;

  function toggleDarkMode() {
    isDarkMode = !isDarkMode;
    try {
      localStorage.setItem("verifai_inpage_dark", isDarkMode ? "true" : "false");
    } catch {}

    if (triggerBtn) {
      triggerBtn.classList.toggle("verifai-dark", isDarkMode);
    }
    if (tooltip) {
      tooltip.classList.toggle("verifai-dark", isDarkMode);
      const iconWrap = tooltip.querySelector(".verifai-theme-toggle-btn");
      if (iconWrap) {
        iconWrap.innerHTML = isDarkMode ? SUN_SVG : MOON_SVG;
      }
    }
    if (imageResultModal) {
      imageResultModal.classList.toggle("verifai-dark", isDarkMode);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // PART 1: HIGHLIGHT TRIGGER PILL ("Analyze Text" & "Check News Validity")
  // ═══════════════════════════════════════════════════════════════════════════

  function ensureTriggerBtn() {
    if (triggerBtn && document.body.contains(triggerBtn)) return triggerBtn;

    triggerBtn = document.createElement("div");
    triggerBtn.id = BTN_ID;
    if (isDarkMode) triggerBtn.classList.add("verifai-dark");

    triggerBtn.innerHTML = `
      <div class="verifai-pill-brand" title="VeriFai Truth Verification">
        ${BRAND_EMBLEM_HTML}
        <span>Verif<span style="color:#f4b400">.</span>ai</span>
      </div>
      <button type="button" class="verifai-pill-btn primary" id="verifai-btn-analyze-text" title="Detect AI vs Human writing">
        ${SPARK_SVG} <span>Analyze Text</span>
      </button>
      <button type="button" class="verifai-pill-btn secondary" id="verifai-btn-check-news" title="Verify news claim against Philippine sources">
        ${NEWSPAPER_SVG} <span>Check News Validity</span>
      </button>
    `;

    document.body.appendChild(triggerBtn);

    // Prevent Facebook/page mousedown from clearing text selection
    triggerBtn.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, true);

    triggerBtn.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, true);

    // Button 1: Analyze Text
    const textBtn = triggerBtn.querySelector("#verifai-btn-analyze-text");
    textBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      executeAnalysis("text");
    }, true);

    // Button 2: Check News Validity
    const newsBtn = triggerBtn.querySelector("#verifai-btn-check-news");
    newsBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      executeAnalysis("news");
    }, true);

    return triggerBtn;
  }

  function showTriggerBtn(rect) {
    if (isAnalyzingText) return;

    const btn = ensureTriggerBtn();
    btn.classList.remove("verifai-visible");
    btn.style.display = "inline-flex";

    const btnWidth = btn.offsetWidth || 300;
    const btnHeight = btn.offsetHeight || 36;

    let left = rect.left + window.scrollX + rect.width / 2 - btnWidth / 2;
    let top = rect.top + window.scrollY - btnHeight - 8;

    if (rect.top < btnHeight + 8) {
      top = rect.bottom + window.scrollY + 8;
    }

    const maxLeft = Math.max(0, document.documentElement.scrollWidth - btnWidth - 10);
    left = Math.max(10, Math.min(left, maxLeft));

    btn.style.left = `${left}px`;
    btn.style.top = `${top}px`;

    requestAnimationFrame(() => {
      btn.classList.add("verifai-visible");
    });
  }

  function hideTriggerBtn() {
    if (isAnalyzingText) return;
    if (triggerBtn) {
      triggerBtn.classList.remove("verifai-visible");
      const ref = triggerBtn;
      setTimeout(() => {
        if (ref && !ref.classList.contains("verifai-visible") && !isAnalyzingText) {
          ref.remove();
          if (triggerBtn === ref) triggerBtn = null;
        }
      }, 140);
    }
  }

  async function executeAnalysis(mode = "text") {
    if (isAnalyzingText) return;
    const textToAnalyze = savedSelectionText;
    const rectToUse = savedSelectionRect;

    if (!textToAnalyze || textToAnalyze.length < MIN_SELECTION_LENGTH) {
      console.warn("[VeriFai] Selected text is too short:", textToAnalyze);
      return;
    }

    if (!chrome?.runtime?.id) {
      alert("VeriFai Extension was reloaded in Chrome. Please refresh (F5) this webpage to reconnect!");
      return;
    }

    isAnalyzingText = true;

    // Show immediate spinner in the clicked button
    const targetBtn = triggerBtn?.querySelector(
      mode === "news" ? "#verifai-btn-check-news" : "#verifai-btn-analyze-text"
    );
    if (targetBtn) {
      targetBtn.innerHTML = `
        <span class="verifai-spinner ${mode === "news" && !isDarkMode ? "dark-spin" : ""}"></span>
        <span>Checking…</span>
      `;
      targetBtn.classList.add("loading");
    }

    try {
      console.log(`[VeriFai] Sending ${mode} analysis request...`);
      const messageType = mode === "news" ? "VERIFY_NEWS" : "ANALYZE_TEXT";
      const response = await chrome.runtime.sendMessage({
        type: messageType,
        text: textToAnalyze,
      });

      if (!response || response.error) {
        throw new Error(response?.error || "No response received from VeriFai.");
      }

      showResultTooltip(response, rectToUse, mode);
    } catch (err) {
      console.error("[VeriFai] Analysis failed:", err);
      showResultTooltip({
        error: true,
        message: err.message || "Could not complete analysis.",
      }, rectToUse, mode);
    } finally {
      isAnalyzingText = false;
      if (triggerBtn) {
        triggerBtn.remove();
        triggerBtn = null;
      }
    }
  }

  // ─── Floating Result Card / Popup ──────────────────────────────────────────
  function safeResult(value, key = "") {
    if (typeof value === "string") {
      if (key === "url") {
        try { if (!["http:", "https:"].includes(new URL(value).protocol)) return "#"; } catch { return "#"; }
      }
      return value.replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
    }
    if (Array.isArray(value)) return value.map(item => safeResult(item));
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k,v]) => [k,safeResult(v,k)]));
    return value;
  }

  function buildResultHTML(result, mode) {
    result = safeResult(result);
    const themeIcon = isDarkMode ? SUN_SVG : MOON_SVG;

    if (result.error) {
      return `
        <div class="verifai-card-topbar">
          <div class="verifai-card-brand-col">
            ${BRAND_EMBLEM_HTML}
            <span>VERIFAI</span>
          </div>
          <div class="verifai-card-controls">
            <button class="verifai-theme-toggle-btn" id="verifai-tip-theme-btn" title="Toggle Light/Dark Mode">${themeIcon}</button>
            <button class="verifai-close-btn" id="verifai-tip-close" aria-label="Close">&times;</button>
          </div>
        </div>
        <div class="verifai-verdict-pill warning">${ALERT_SVG} Notice</div>
        <h4 class="verifai-card-title">Analysis Incomplete</h4>
        <p class="verifai-card-desc">${result.message || "Check backend connectivity at http://localhost:8000."}</p>
        <div class="verifai-tooltip-footer">
          <span>VeriFai Extension</span>
        </div>
      `;
    }

    // News Verification Result
    if (mode === "news" || result.kind === "news") {
      const v = result.verdict || "UNVERIFIED";
      const isReal = v === "VERIFIED" || v === "LIKELY_TRUE";
      const isFake = v === "FALSE" || v === "LIKELY_FALSE";
      const tone = isReal ? "real" : isFake ? "fake" : "warning";
      const labels = {
        VERIFIED: "Real News",
        LIKELY_TRUE: "Likely Real",
        MISLEADING: "Misleading",
        UNVERIFIED: "Unverified",
        LIKELY_FALSE: "Likely Fake",
        FALSE: "Fake News",
      };

      const closestStoryHtml = result.closestStory?.found
        ? `
          <div class="verifai-news-evidence">
            <small>CLOSEST VERIFIED REPORT</small>
            <a href="${result.closestStory.url}" target="_blank" rel="noreferrer">
              ${result.closestStory.title} &rarr;
            </a>
          </div>
        `
        : "";

      return `
        <div class="verifai-card-topbar">
          <div class="verifai-card-brand-col">
            ${BRAND_EMBLEM_HTML}
            <span>PHILIPPINE FACT-CHECK</span>
          </div>
          <div class="verifai-card-controls">
            <button class="verifai-theme-toggle-btn" id="verifai-tip-theme-btn" title="Toggle Light/Dark Mode">${themeIcon}</button>
            <button class="verifai-close-btn" id="verifai-tip-close" aria-label="Close">&times;</button>
          </div>
        </div>
        <div class="verifai-verdict-pill ${tone}">
          ${isReal ? CHECK_SVG : ALERT_SVG} ${labels[v] || v} · ${result.confidence || 0}%
        </div>
        <h4 class="verifai-card-title">${isReal ? "Matches Verified News Outlets" : isFake ? "Debunked Claim / Disinformation" : "Context Review Recommended"}</h4>
        <p class="verifai-card-desc">${result.explanation || "Cross-referenced against Philippine fact-check archives."}</p>
        ${closestStoryHtml}
        <div class="verifai-tooltip-footer">
          <span>VeriFai Fact-Check Engine</span>
          <button class="verifai-copy-btn" id="verifai-copy-tooltip-text">Copy Summary</button>
        </div>
      `;
    }

    // AI Writing Result
    const isAI = result.classification === "Likely AI-generated";
    const isHuman = result.classification === "Likely human-written";
    const tone = isAI ? "fake" : isHuman ? "real" : "warning";
    const aiScore = result.aiProbability ?? result.confidence ?? 50;
    const humanScore = result.humanProbability ?? (100 - aiScore);

    const signalsHtml = (result.signals && result.signals.length > 0)
      ? `
        <div class="verifai-tags-row">
          ${result.signals.slice(0, 3).map((s) => `<span class="verifai-tag">${s}</span>`).join("")}
        </div>
      `
      : "";

    return `
      <div class="verifai-card-topbar">
        <div class="verifai-card-brand-col">
          ${BRAND_EMBLEM_HTML}
          <span>WRITING AUTHENTICITY</span>
        </div>
        <div class="verifai-card-controls">
          <button class="verifai-theme-toggle-btn" id="verifai-tip-theme-btn" title="Toggle Light/Dark Mode">${themeIcon}</button>
          <button class="verifai-close-btn" id="verifai-tip-close" aria-label="Close">&times;</button>
        </div>
      </div>
      <div class="verifai-verdict-pill ${tone}">
        ${isAI ? ALERT_SVG : CHECK_SVG} ${result.classification || (isAI ? "Likely AI-generated" : "Likely human-written")}
      </div>
      <h4 class="verifai-card-title">${isAI ? "Likely AI-Generated Writing" : isHuman ? "Natural Human Writing" : "Mixed Characteristics"}</h4>
      <p class="verifai-card-desc">${result.scoreInterpretation || (isAI ? "Contains uniform sentence rhythm and repetitive chatbot syntax." : "Exhibits natural colloquial variations and human rhythm.")}</p>

      <div class="verifai-bars">
        <div class="verifai-bar-row">
          <div class="verifai-bar-labels">
            <span>AI Writing Likelihood</span>
            <strong>${aiScore}%</strong>
          </div>
          <div class="verifai-bar-track">
            <div class="verifai-bar-fill ai" style="width: ${aiScore}%;"></div>
          </div>
        </div>
        <div class="verifai-bar-row">
          <div class="verifai-bar-labels">
            <span>Human Writing Likelihood</span>
            <strong>${humanScore}%</strong>
          </div>
          <div class="verifai-bar-track">
            <div class="verifai-bar-fill human" style="width: ${humanScore}%;"></div>
          </div>
        </div>
      </div>

      ${signalsHtml}

      <div class="verifai-tooltip-footer">
        <span>${result.details?.model || "XLM-RoBERTa"} · ${result.confidence ?? 0}% conf</span>
        <button class="verifai-copy-btn" id="verifai-copy-tooltip-text">Copy Summary</button>
      </div>
    `;
  }

  function showResultTooltip(result, rect, mode) {
    hideResultTooltip();

    tooltip = document.createElement("div");
    tooltip.id = TOOLTIP_ID;
    if (isDarkMode) tooltip.classList.add("verifai-dark");

    tooltip.innerHTML = buildResultHTML(result, mode);
    document.body.appendChild(tooltip);

    // Dark Mode Toggle inside Tooltip
    const themeBtn = tooltip.querySelector("#verifai-tip-theme-btn");
    if (themeBtn) {
      themeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleDarkMode();
      });
    }

    // Close Button
    const closeBtn = tooltip.querySelector("#verifai-tip-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        hideResultTooltip();
      });
    }

    // Copy Button
    const copyBtn = tooltip.querySelector("#verifai-copy-tooltip-text");
    if (copyBtn) {
      copyBtn.addEventListener("click", (e) => {
        e.preventDefault();
        const copyText = `VeriFai Verdict: ${result.classification || result.verdict || "Analyzed"} (${result.confidence || 0}%)\n${result.explanation || result.scoreInterpretation || ""}`;
        navigator.clipboard.writeText(copyText).then(() => {
          copyBtn.textContent = "Copied!";
          setTimeout(() => { if (copyBtn) copyBtn.textContent = "Copy Summary"; }, 1500);
        });
      });
    }

    tooltip.addEventListener("mousedown", (e) => e.stopPropagation());

    positionTooltip(rect);
    requestAnimationFrame(() => tooltip.classList.add("verifai-visible"));
  }

  function positionTooltip(rect) {
    if (!tooltip) return;

    const width = 340;
    tooltip.style.visibility = "hidden";
    tooltip.style.display = "block";
    const height = tooltip.offsetHeight || 280;
    tooltip.style.visibility = "";

    const targetRect = rect || {
      top: window.innerHeight / 2 - 100,
      bottom: window.innerHeight / 2,
      left: window.innerWidth / 2 - width / 2,
      width: width,
    };

    let top;
    if (targetRect.top >= height + 10) {
      top = targetRect.top + window.scrollY - height - 10;
    } else {
      top = targetRect.bottom + window.scrollY + 10;
    }

    let left = targetRect.left + window.scrollX + targetRect.width / 2 - width / 2;
    const maxLeft = Math.max(0, document.documentElement.scrollWidth - width - 12);
    left = Math.max(12, Math.min(left, maxLeft));

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function hideResultTooltip() {
    if (tooltip) {
      tooltip.classList.remove("verifai-visible");
      const ref = tooltip;
      setTimeout(() => {
        if (ref) ref.remove();
      }, 160);
      tooltip = null;
    }
  }

  // ─── Selection Detection ───────────────────────────────────────────────────
  function handleSelectionChange() {
    if (isAnalyzingText || snipOverlay) return;

    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
        hideTriggerBtn();
        return;
      }

      const text = sel.toString().trim();
      if (text.length < MIN_SELECTION_LENGTH) {
        hideTriggerBtn();
        return;
      }

      savedSelectionText = text;
      try {
        const range = sel.getRangeAt(0);
        let rect = range.getBoundingClientRect();

        if ((!rect || (rect.width === 0 && rect.height === 0)) && range.getClientRects().length > 0) {
          rect = range.getClientRects()[0];
        }

        if (rect && (rect.width > 0 || rect.height > 0)) {
          savedSelectionRect = {
            top: rect.top,
            bottom: rect.bottom,
            left: rect.left,
            right: rect.right,
            width: rect.width,
            height: rect.height,
          };
          showTriggerBtn(savedSelectionRect);
        }
      } catch (err) {
        console.warn("[VeriFai] Selection rect error:", err);
      }
    }, DEBOUNCE_MS);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // PART 2: IN-PAGE IMAGE CUT & RESULT WORKFLOW
  // ═══════════════════════════════════════════════════════════════════════════

  async function startInPageImageSnip(screenshotDataUrl, initialMode = "media") {
    hideTriggerBtn();
    hideResultTooltip();
    hideImageResultModal();
    hideInPageLoader();
    if (snipOverlay) snipOverlay.remove();

    let screenshot = screenshotDataUrl;
    if (!screenshot) {
      try {
        const res = await chrome.runtime.sendMessage({ type: "REQUEST_TAB_SCREENSHOT" });
        if (!res?.ok || !res?.screenshot) {
          throw new Error(res?.error || "Could not capture tab screenshot.");
        }
        screenshot = res.screenshot;
      } catch (err) {
        alert("VeriFai Screenshot: " + (err.message || "Failed to capture page."));
        return;
      }
    }

    const img = new Image();
    img.onload = () => {
      renderSnipperOverlay(img, initialMode);
    };
    img.src = screenshot;
  }

  function renderSnipperOverlay(loadedImg, defaultMode) {
    let currentMode = defaultMode || "media";
    let isDragging = false;
    let dragStart = null;
    let currentSelection = null;

    snipOverlay = document.createElement("div");
    snipOverlay.id = SNIP_OVERLAY_ID;

    snipOverlay.innerHTML = `
      <canvas id="verifai-snip-canvas"></canvas>
      <div class="verifai-snip-topbar">
        <span class="verifai-snip-badge">
          ${BRAND_EMBLEM_HTML}
          <span>VeriFai Image Cut</span>
        </span>
        <span class="verifai-snip-hint">Click &amp; drag across any visual region to verify</span>
        <button type="button" class="verifai-snip-cancel-btn" id="verifai-snip-esc-btn">Esc to Cancel</button>
      </div>
      <div id="${SNIP_TOOLBAR_ID}" style="display: none;">
        <div class="verifai-snip-mode-select">
          <button type="button" class="verifai-snip-mode-btn ${currentMode === "media" ? "active" : ""}" data-mode="media">Visual AI Forensics</button>
          <button type="button" class="verifai-snip-mode-btn ${currentMode === "news_image" ? "active" : ""}" data-mode="news_image">News Graphic OCR</button>
        </div>
        <button type="button" class="verifai-snip-confirm-btn" id="verifai-snip-analyze-btn">
          ${SPARK_SVG} <span>Analyze</span>
        </button>
        <button type="button" class="verifai-snip-cancel-action-btn" id="verifai-snip-redo-btn">Redo</button>
      </div>
    `;

    document.body.appendChild(snipOverlay);

    const canvas = snipOverlay.querySelector("#verifai-snip-canvas");
    const toolbar = snipOverlay.querySelector(`#${SNIP_TOOLBAR_ID}`);
    const ctx = canvas.getContext("2d");

    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;

    const scaleX = loadedImg.naturalWidth / width;
    const scaleY = loadedImg.naturalHeight / height;

    function draw() {
      ctx.clearRect(0, 0, width, height);
      ctx.drawImage(loadedImg, 0, 0, width, height);

      if (currentSelection) {
        const { startX, startY, endX, endY } = currentSelection;
        const x = Math.min(startX, endX);
        const y = Math.min(startY, endY);
        const w = Math.abs(endX - startX);
        const h = Math.abs(endY - startY);

        ctx.fillStyle = "rgba(9, 9, 12, 0.65)";
        ctx.fillRect(0, 0, width, height);

        ctx.save();
        ctx.beginPath();
        ctx.rect(x, y, w, h);
        ctx.clip();
        ctx.drawImage(loadedImg, 0, 0, width, height);
        ctx.restore();

        ctx.strokeStyle = "#ef1717";
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);

        ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.strokeRect(x, y, w, h);
        ctx.setLineDash([]);

        if (w > 60 && h > 26) {
          const badgeText = `${Math.round(w * scaleX)} × ${Math.round(h * scaleY)} px`;
          ctx.font = '700 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
          const textW = ctx.measureText(badgeText).width;
          ctx.fillStyle = "rgba(9, 9, 12, 0.88)";
          ctx.fillRect(x + w / 2 - textW / 2 - 8, y + h / 2 - 10, textW + 16, 20);
          ctx.fillStyle = "#ffffff";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(badgeText, x + w / 2, y + h / 2);
        }
      }
    }

    draw();

    canvas.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      isDragging = true;
      dragStart = { x: e.clientX, y: e.clientY };
      currentSelection = { startX: e.clientX, startY: e.clientY, endX: e.clientX, endY: e.clientY };
      toolbar.style.display = "none";
      draw();
    });

    const onMouseMove = (e) => {
      if (!isDragging || !dragStart) return;
      currentSelection = {
        startX: dragStart.x,
        startY: dragStart.y,
        endX: Math.max(0, Math.min(e.clientX, width)),
        endY: Math.max(0, Math.min(e.clientY, height)),
      };
      draw();
    };

    const onMouseUp = () => {
      if (!isDragging) return;
      isDragging = false;
      if (!currentSelection) return;

      const w = Math.abs(currentSelection.endX - currentSelection.startX);
      const h = Math.abs(currentSelection.endY - currentSelection.startY);

      if (w < 15 || h < 15) {
        currentSelection = null;
        toolbar.style.display = "none";
        draw();
        return;
      }

      const selX = Math.min(currentSelection.startX, currentSelection.endX);
      const selY = Math.min(currentSelection.startY, currentSelection.endY);
      toolbar.style.display = "flex";
      const tbWidth = toolbar.offsetWidth || 280;
      let tbLeft = selX + w / 2 - tbWidth / 2;
      tbLeft = Math.max(12, Math.min(tbLeft, width - tbWidth - 12));

      let tbTop = selY + h + 10;
      if (tbTop + 40 > height) {
        tbTop = Math.max(12, selY - 44);
      }

      toolbar.style.left = `${tbLeft}px`;
      toolbar.style.top = `${tbTop}px`;
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    toolbar.querySelectorAll(".verifai-snip-mode-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        toolbar.querySelectorAll(".verifai-snip-mode-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentMode = btn.dataset.mode;
      });
    });

    toolbar.querySelector("#verifai-snip-redo-btn").addEventListener("click", () => {
      currentSelection = null;
      toolbar.style.display = "none";
      draw();
    });

    const cancelSnip = () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("keydown", onKeyDown);
      if (snipOverlay) {
        snipOverlay.remove();
        snipOverlay = null;
      }
    };

    snipOverlay.querySelector("#verifai-snip-esc-btn").addEventListener("click", cancelSnip);

    function onKeyDown(e) {
      if (e.key === "Escape") {
        cancelSnip();
      } else if (e.key === "Enter" && currentSelection) {
        executeAnalysis();
      }
    }
    window.addEventListener("keydown", onKeyDown);

    toolbar.querySelector("#verifai-snip-analyze-btn").addEventListener("click", executeAnalysis);

    async function executeAnalysis() {
      if (!currentSelection) return;

      const { startX, startY, endX, endY } = currentSelection;
      const x = Math.min(startX, endX);
      const y = Math.min(startY, endY);
      const w = Math.abs(endX - startX);
      const h = Math.abs(endY - startY);

      const cropX = Math.round(x * scaleX);
      const cropY = Math.round(y * scaleY);
      const cropW = Math.round(w * scaleX);
      const cropH = Math.round(h * scaleY);

      const offCanvas = document.createElement("canvas");
      offCanvas.width = cropW;
      offCanvas.height = cropH;
      const offCtx = offCanvas.getContext("2d");
      offCtx.drawImage(loadedImg, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);

      const croppedDataUrl = offCanvas.toDataURL("image/png");

      cancelSnip();
      showInPageLoader(currentMode);

      try {
        const response = await chrome.runtime.sendMessage({
          type: "ANALYZE_IMAGE",
          croppedImage: croppedDataUrl,
          mode: currentMode,
        });

        hideInPageLoader();
        showImageResultModal(response || {}, croppedDataUrl, currentMode);
      } catch (err) {
        hideInPageLoader();
        console.error("[VeriFai Content] Image analysis failed:", err);
        showImageResultModal({
          error: true,
          label: "Analysis Error",
          summary: err.message || "Failed to analyze image.",
        }, croppedDataUrl, currentMode);
      }
    }
  }

  // ─── In-Page Loader Card ───────────────────────────────────────────────────
  function showInPageLoader(mode) {
    hideInPageLoader();
    inpageLoader = document.createElement("div");
    inpageLoader.id = LOADER_ID;
    inpageLoader.innerHTML = `
      <div class="verifai-loader-icon">
        ${CROP_SVG}
      </div>
      <h3 class="verifai-loader-title">${mode === "news_image" ? "Fact-Checking Graphic…" : "Inspecting Visual AI Forensics…"}</h3>
      <p class="verifai-loader-sub">${mode === "news_image" ? "Extracting headlines with OCR & cross-referencing news archives…" : "Scanning image for frequency anomalies, warping & diffusion artifacts…"}</p>
    `;
    document.body.appendChild(inpageLoader);
  }

  function hideInPageLoader() {
    if (inpageLoader) {
      inpageLoader.remove();
      inpageLoader = null;
    }
  }

  // ─── In-Page Image Forensics Result Modal ──────────────────────────────────
  function showImageResultModal(result, croppedDataUrl, mode) {
    result = safeResult(result);
    hideImageResultModal();

    imageResultModal = document.createElement("div");
    imageResultModal.id = MODAL_ID;
    if (isDarkMode) imageResultModal.classList.add("verifai-dark");

    const themeIcon = isDarkMode ? SUN_SVG : MOON_SVG;

    if (result.error) {
      result.summary = result.summary || result.error;
      imageResultModal.innerHTML = `
        <div class="verifai-modal-head-row">
          <div class="verifai-modal-brand">
            ${BRAND_EMBLEM_HTML}
            <span>IMAGE FORENSICS</span>
          </div>
          <button class="verifai-close-btn" id="verifai-modal-close">&times;</button>
        </div>
        ${croppedDataUrl ? `<img src="${croppedDataUrl}" class="verifai-thumb-preview" alt="Cropped area" />` : ""}
        <div class="verifai-verdict-pill warning">${ALERT_SVG} Notice</div>
        <h4 class="verifai-card-title">Forensic Scan</h4>
        <p class="verifai-card-desc">${result.summary || "Could not complete image forensics request."}</p>
        <div class="verifai-modal-actions">
          <button class="verifai-btn-dismiss" id="verifai-modal-done">Close</button>
        </div>
      `;
    } else if (mode === "news_image" || result.kind === "news_image") {
      const v = result.classification || result.label || "UNVERIFIED";
      const isReal = v === "REAL" || v === "VERIFIED" || v === "LIKELY_TRUE";
      const isFake = v === "FAKE" || v === "FALSE" || v === "LIKELY_FALSE";
      const tone = isReal ? "real" : isFake ? "fake" : "warning";

      const ocrHtml = result.ocr?.full_text
        ? `<div class="verifai-ocr-block"><small>Extracted Graphic Text (OCR)</small><div class="verifai-ocr-text">"${result.ocr.full_text.slice(0, 180)}…"</div></div>`
        : "";

      const closestStoryHtml = result.closestStory?.found
        ? `
          <div class="verifai-news-evidence">
            <small>CLOSEST VERIFIED REPORT</small>
            <a href="${result.closestStory.url}" target="_blank" rel="noreferrer">
              ${result.closestStory.title} &rarr;
            </a>
          </div>
        `
        : "";

      imageResultModal.innerHTML = `
        <div class="verifai-modal-head-row">
          <div class="verifai-modal-brand">
            ${BRAND_EMBLEM_HTML}
            <span>NEWS GRAPHIC FACT-CHECK</span>
          </div>
          <button class="verifai-close-btn" id="verifai-modal-close">&times;</button>
        </div>
        ${croppedDataUrl ? `<img src="${croppedDataUrl}" class="verifai-thumb-preview" alt="Cropped region" />` : ""}
        <div class="verifai-verdict-pill ${tone}">
          ${isReal ? CHECK_SVG : ALERT_SVG} ${v} · ${result.confidence || 0}%
        </div>
        <h4 class="verifai-card-title">${isReal ? "Verified Graphic or Statement" : isFake ? "Debunked or Altered News Card" : "Unverified News Graphic"}</h4>
        <p class="verifai-card-desc">${result.reasoningSummary || "Evaluated against Philippine news publisher archives & OCR analysis."}</p>
        ${ocrHtml}
        ${closestStoryHtml}
        <div class="verifai-modal-actions">
          <button class="verifai-btn-dismiss" id="verifai-modal-done">Done</button>
          <button class="verifai-btn-copy-modal" id="verifai-modal-copy">Copy Result</button>
        </div>
      `;
    } else {
      const isAI = result.isAIGenerated || result.label === "Likely AI-generated";
      const tone = isAI ? "fake" : "real";
      const aiScore = result.aiProbability ?? result.confidence ?? 50;
      const authScore = result.authenticProbability ?? (100 - aiScore);

      const signalsHtml = (result.signals && result.signals.length > 0)
        ? `<div class="verifai-tags-row">${result.signals.map((s) => `<span class="verifai-tag">${s}</span>`).join("")}</div>`
        : "";

      imageResultModal.innerHTML = `
        <div class="verifai-modal-head-row">
          <div class="verifai-modal-brand">
            ${BRAND_EMBLEM_HTML}
            <span>VISUAL AI FORENSICS</span>
          </div>
          <button class="verifai-close-btn" id="verifai-modal-close">&times;</button>
        </div>
        ${croppedDataUrl ? `<img src="${croppedDataUrl}" class="verifai-thumb-preview" alt="Cropped region" />` : ""}
        <div class="verifai-verdict-pill ${tone}">
          ${isAI ? ALERT_SVG : CHECK_SVG} ${result.label || (isAI ? "Likely AI-generated" : "Likely camera-captured")} · ${result.confidence || 0}%
        </div>
        <h4 class="verifai-card-title">${isAI ? "AI-Generated Visual Artifacts Detected" : "Consistent Camera & Authentic Pixel Patterns"}</h4>
        <p class="verifai-card-desc">${result.summary || (isAI ? "Exhibits generative smoothing, synthetic light reflections, and unnatural texture coherence." : "Contains authentic camera noise, consistent lighting, and organic pixel distributions.")}</p>

        <div class="verifai-bars">
          <div class="verifai-bar-row">
            <div class="verifai-bar-labels">
              <span>AI Generation Likelihood</span>
              <strong>${aiScore}%</strong>
            </div>
            <div class="verifai-bar-track">
              <div class="verifai-bar-fill ai" style="width: ${aiScore}%;"></div>
            </div>
          </div>
          <div class="verifai-bar-row">
            <div class="verifai-bar-labels">
              <span>Authentic Camera Likelihood</span>
              <strong>${authScore}%</strong>
            </div>
            <div class="verifai-bar-track">
              <div class="verifai-bar-fill human" style="width: ${authScore}%;"></div>
            </div>
          </div>
        </div>

        ${signalsHtml}

        <div class="verifai-modal-actions">
          <button class="verifai-btn-dismiss" id="verifai-modal-done">Done</button>
          <button class="verifai-btn-copy-modal" id="verifai-modal-copy">Copy Result</button>
        </div>
      `;
    }

    document.body.appendChild(imageResultModal);

    const closeBtn = imageResultModal.querySelector("#verifai-modal-close");
    const doneBtn = imageResultModal.querySelector("#verifai-modal-done");
    const copyBtn = imageResultModal.querySelector("#verifai-modal-copy");

    if (closeBtn) closeBtn.addEventListener("click", hideImageResultModal);
    if (doneBtn) doneBtn.addEventListener("click", hideImageResultModal);

    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const text = `VeriFai Image Forensics: ${result.label || result.classification} (${result.confidence || 0}%)\n${result.summary || result.reasoningSummary || ""}`;
        navigator.clipboard.writeText(text).then(() => {
          copyBtn.textContent = "Copied!";
          setTimeout(() => { if (copyBtn) copyBtn.textContent = "Copy Result"; }, 1400);
        });
      });
    }

    const escListener = (e) => {
      if (e.key === "Escape") {
        hideImageResultModal();
        window.removeEventListener("keydown", escListener);
      }
    };
    window.addEventListener("keydown", escListener);
  }

  function hideImageResultModal() {
    if (imageResultModal) {
      imageResultModal.remove();
      imageResultModal = null;
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GLOBAL LISTENERS
  // ═══════════════════════════════════════════════════════════════════════════

  document.addEventListener("keydown", (e) => {
    if (e.altKey && e.shiftKey && (e.code === "KeyF" || e.key === "F" || e.key === "f" || e.code === "KeyS" || e.key === "S" || e.key === "s")) {
      e.preventDefault();
      startInPageImageSnip(null, "media");
    }
  });

  document.addEventListener("selectionchange", handleSelectionChange, { passive: true });
  document.addEventListener("mouseup", () => {
    setTimeout(handleSelectionChange, 10);
  }, { passive: true });

  document.addEventListener("mousedown", (e) => {
    if (triggerBtn && (triggerBtn === e.target || triggerBtn.contains(e.target))) return;
    if (tooltip && (tooltip === e.target || tooltip.contains(e.target))) return;
    if (imageResultModal && (imageResultModal === e.target || imageResultModal.contains(e.target))) return;
    if (snipOverlay && (snipOverlay === e.target || snipOverlay.contains(e.target))) return;

    hideTriggerBtn();
    hideResultTooltip();
  }, true);

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "TRIGGER_IMAGE_SNIP") {
      startInPageImageSnip(message.screenshot, message.mode || "media");
      sendResponse({ ok: true });
      return true;
    }
    if (message.type === "FACTGUARD_PING" || message.type === "VERIFAI_PING") {
      sendResponse({ ok: true });
      return true;
    }
  });

  console.log("[VeriFai] Theme synchronized with VeriFai brand. Highlight text to see Analyze Text & Check News Validity buttons.");
})();
