import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  FileImage,
  FileText,
  History,
  Info,
  LayoutDashboard,
  Lock,
  LogOut,
  MousePointer2,
  Newspaper,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  X,
} from "lucide-react";
import {
  checkBackendHealth,
  getCurrentUser,
  loginUser,
  logoutUser,
} from "../utils/api.js";
import {
  clearScanHistory,
  getScanHistory,
} from "../utils/storage.js";

import { DASHBOARD_URL } from "../../public/config.js";

function formatTimestamp(isoString) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "";
    const now = new Date();
    const isToday =
      d.getDate() === now.getDate() &&
      d.getMonth() === now.getMonth() &&
      d.getFullYear() === now.getFullYear();

    const timeStr = d.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    if (isToday) return `Today, ${timeStr}`;
    return `${d.toLocaleDateString([], { month: "short", day: "numeric" })}, ${timeStr}`;
  } catch {
    return "";
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState("history"); // "history" | "dashboard"
  const [backendOnline, setBackendOnline] = useState(false);
  const [user, setUser] = useState(null);
  const [showAuthModal, setShowAuthModal] = useState(false);

  // Auth form state
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  // History state
  const [scanHistory, setScanHistory] = useState([]);
  const [historyFilter, setHistoryFilter] = useState("all"); // "all" | "text" | "news" | "media"
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedScan, setSelectedScan] = useState(null); // Detailed modal
  const [copiedDetail, setCopiedDetail] = useState(false);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  // ─── Load state ──────────────────────────────────────────────────────────
  const loadState = useCallback(async () => {
    try {
      const [history, currentUser] = await Promise.all([
        getScanHistory(),
        getCurrentUser(),
      ]);
      setScanHistory(history || []);
      setUser(currentUser);
    } catch (err) {
      console.error("[VeriFai Popup] State read error:", err);
    }
  }, []);

  const checkHealth = useCallback(async () => {
    setIsCheckingHealth(true);
    try {
      const health = await checkBackendHealth();
      setBackendOnline(health.ok);
    } finally {
      setIsCheckingHealth(false);
    }
  }, []);

  useEffect(() => {
    loadState();
    checkHealth();
    const onChange = (changes) => {
      if (changes.verifai_scan_history) setScanHistory(changes.verifai_scan_history.newValue || []);
      if (changes.verifai_auth) setUser(changes.verifai_auth.newValue?.user || null);
    };
    globalThis.chrome?.storage?.onChanged?.addListener(onChange);
    return () => globalThis.chrome?.storage?.onChanged?.removeListener(onChange);
  }, [loadState, checkHealth]);

  useEffect(() => {
    if (!showAuthModal && !selectedScan) return;
    const previous = document.activeElement;
    const dialog = document.querySelector('[role="dialog"]');
    const focusable = () => [...dialog.querySelectorAll('button:not(:disabled), input, a[href], [tabindex="0"]')];
    focusable()[0]?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") { setShowAuthModal(false); setSelectedScan(null); }
      if (event.key !== "Tab") return;
      const nodes = focusable();
      const first = nodes[0], last = nodes.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); previous?.focus(); };
  }, [showAuthModal, selectedScan]);

  // ─── Filtered & Searched History ─────────────────────────────────────────
  const filteredHistory = useMemo(() => {
    return scanHistory.filter((item) => {
      // Kind filter
      if (historyFilter !== "all") {
        if (historyFilter === "text" && item.kind !== "text") return false;
        if (historyFilter === "news" && item.kind !== "news") return false;
        if (
          historyFilter === "media" &&
          item.kind !== "media" &&
          item.kind !== "news_image"
        )
          return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const titleMatch = (item.title || item.snippet || "").toLowerCase().includes(q);
        const verdictMatch = (
          item.result?.classification ||
          item.result?.verdict ||
          item.result?.label ||
          ""
        )
          .toLowerCase()
          .includes(q);
        return titleMatch || verdictMatch;
      }

      return true;
    });
  }, [scanHistory, historyFilter, searchQuery]);

  // ─── Computed Dashboard Statistics ───────────────────────────────────────
  const stats = useMemo(() => {
    const total = scanHistory.length;
    if (total === 0) {
      return { total: 0, authentic: 0, aiOrFake: 0, authenticPct: 0, aiOrFakePct: 0 };
    }

    let authentic = 0;
    let aiOrFake = 0;

    scanHistory.forEach((item) => {
      const res = item.result;
      if (!res) return;

      if (item.kind === "text") {
        if (res.classification === "Likely human-written") authentic++;
        else if (res.classification === "Likely AI-generated") aiOrFake++;
      } else if (item.kind === "news") {
        if (res.verdict === "VERIFIED" || res.verdict === "LIKELY_TRUE") authentic++;
        else if (res.verdict === "FALSE" || res.verdict === "LIKELY_FALSE" || res.verdict === "MISLEADING") aiOrFake++;
      } else if (item.kind === "media" || item.kind === "news_image") {
        if (res.isAIGenerated || res.label === "Likely AI-generated" || res.classification === "FAKE") aiOrFake++;
        else if (res.label === "Likely authentic/camera-captured" || res.classification === "REAL") authentic++;
      }
    });

    return {
      total,
      authentic,
      aiOrFake,
      authenticPct: total > 0 ? Math.round((authentic / total) * 100) : 0,
      aiOrFakePct: total > 0 ? Math.round((aiOrFake / total) * 100) : 0,
    };
  }, [scanHistory]);

  // ─── Clear History ────────────────────────────────────────────────────────
  const handleClearHistory = async () => {
    if (window.confirm("Are you sure you want to clear your local verification history?")) {
      await clearScanHistory();
      setScanHistory([]);
      setSelectedScan(null);
    }
  };

  // ─── Login & Auth ─────────────────────────────────────────────────────────
  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError("");
    setIsLoggingIn(true);
    try {
      const auth = await loginUser(authEmail, authPassword);
      setUser(auth.user);
      setShowAuthModal(false);
      setAuthPassword("");
    } catch (err) {
      setAuthError(err.message || "Invalid email or password");
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    await logoutUser();
    setUser(null);
  };

  // ─── Verdict Tone Helper ──────────────────────────────────────────────────
  const getVerdictInfo = (item) => {
    const res = item?.result;
    if (!res) return { label: "Completed", tone: "neutral" };

    if (item.kind === "text") {
      const isAI = res.classification === "Likely AI-generated";
      const isHuman = res.classification === "Likely human-written";
      return {
        label: res.classification || "Scanned",
        tone: isAI ? "fake" : isHuman ? "real" : "warning",
      };
    }

    if (item.kind === "news") {
      const v = res.verdict || "UNVERIFIED";
      const isReal = v === "VERIFIED" || v === "LIKELY_TRUE";
      const isFake = v === "FALSE" || v === "LIKELY_FALSE";
      const labels = {
        VERIFIED: "Real News",
        LIKELY_TRUE: "Likely Real",
        MISLEADING: "Misleading",
        UNVERIFIED: "Unverified",
        LIKELY_FALSE: "Likely Fake",
        FALSE: "Fake News",
      };
      return {
        label: labels[v] || v,
        tone: isReal ? "real" : isFake ? "fake" : "warning",
      };
    }

    if (item.kind === "media" || item.kind === "news_image") {
      const label = res.label || res.classification || "Processed";
      const isFake = res.isAIGenerated || label === "Likely AI-generated" || label === "FAKE";
      const isReal = label === "Likely authentic/camera-captured" || label === "REAL";
      return {
        label: item.kind === "news_image" ? label : isFake ? "AI Generated" : isReal ? "Authentic" : label,
        tone: isReal ? "real" : isFake ? "fake" : "warning",
      };
    }

    return { label: "Scan Result", tone: "neutral" };
  };

  // Copy selected scan details
  const handleCopyScan = () => {
    if (!selectedScan) return;
    const res = selectedScan.result;
    const info = getVerdictInfo(selectedScan);
    const text = `VeriFai Verification: ${selectedScan.title}\nVerdict: ${info.label} (${res?.confidence || 0}%)\nDetails: ${res?.explanation || res?.summary || res?.scoreInterpretation || ""}\nDate: ${new Date(selectedScan.timestamp).toLocaleString()}`;
    navigator.clipboard.writeText(text).then(() => {
      setCopiedDetail(true);
      setTimeout(() => setCopiedDetail(false), 1500);
    });
  };

  return (
    <div className="shell">
      {/* ── Topbar ── */}
      <header className="topbar">
        <div className="brand">
          <img className="brand-symbol" src="icons/brand.svg" alt="" />
          <span className="brand-text">
            <span className="brand-title">Verif<span className="brand-dot">.</span>ai</span>
            <span className="brand-tagline">Clarity before you share</span>
          </span>
        </div>

        <div className="topbar-actions">
          <button
            className="status-chip"
            onClick={checkHealth}
            title={backendOnline ? "VeriFai API Connected" : "Backend Offline — Click to recheck"}
          >
            <span className={`status-dot ${backendOnline ? "" : "offline"}`} />
            <span>{isCheckingHealth ? "Connecting" : backendOnline ? "Connected" : "Offline"}</span>
            {isCheckingHealth && <RefreshCw size={10} className="spin" style={{ marginLeft: 3 }} />}
          </button>

          {user ? (
            <button
              className="user-btn"
              onClick={handleLogout}
              title={`Signed in as ${user.name || user.email}. Click to sign out.`}
            >
              <User size={12} />
              <span>{user.name?.split(" ")[0] || "Account"}</span>
              <LogOut size={10} style={{ marginLeft: 2, opacity: 0.7 }} />
            </button>
          ) : (
            <button
              className="user-btn"
              onClick={() => setShowAuthModal(true)}
              title="Sign in to your VeriFai account"
            >
              <Lock size={11} />
              <span>Sign In</span>
            </button>
          )}
        </div>
      </header>

      {/* ── Focused 2-Tab Navigation: History & Dashboard ── */}
      <nav className="nav-tabs" role="tablist" aria-label="Extension views">
        <button
          className={`tab-btn ${activeTab === "history" ? "active" : ""}`}
          onClick={() => setActiveTab("history")}
          role="tab"
          aria-selected={activeTab === "history"}
        >
          <History size={13} /> History
          {scanHistory.length > 0 && (
            <span className="tab-count-pill">{scanHistory.length}</span>
          )}
        </button>

        <button
          className={`tab-btn ${activeTab === "dashboard" ? "active" : ""}`}
          onClick={() => setActiveTab("dashboard")}
          role="tab"
          aria-selected={activeTab === "dashboard"}
        >
          <LayoutDashboard size={13} /> Dashboard
        </button>
      </nav>

      {/* ── Main Content Area ── */}
      <main className="popup-main">
        {activeTab === "history" && (
          <section className="view-enter">
            {/* Search & Filter Bar */}
            <div className="history-toolbar">
              <div className="search-box">
                <Search size={13} className="search-icon" />
                <input
                  type="text"
                  placeholder="Search scans by text or verdict…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="search-input"
                />
                {searchQuery && (
                  <button
                    className="search-clear-btn"
                    onClick={() => setSearchQuery("")}
                  >
                    <X size={12} />
                  </button>
                )}
              </div>

              <div className="history-filter-row">
                <div className="filter-chips">
                  {[
                    { id: "all", label: "All" },
                    { id: "text", label: "Writing" },
                    { id: "news", label: "News" },
                    { id: "media", label: "Images" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      className={`filter-chip ${historyFilter === f.id ? "active" : ""}`}
                      onClick={() => setHistoryFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>

                {scanHistory.length > 0 && (
                  <button
                    className="clear-history-btn"
                    onClick={handleClearHistory}
                    title="Clear all stored scans"
                  >
                    <Trash2 size={12} /> Clear
                  </button>
                )}
              </div>
            </div>

            {/* History List */}
            {filteredHistory.length === 0 ? (
              <div className="empty-history-card">
                <div className="empty-icon-shell">
                  <History size={26} />
                </div>
                <h3>{scanHistory.length === 0 ? "No Scans Saved Yet" : "No Matching Results"}</h3>
                <p>
                  {scanHistory.length === 0
                    ? "Highlight text on any website to see the Analyze popup, or press Alt+Shift+F to cut an image."
                    : "Try adjusting your search terms or filter."}
                </p>
              </div>
            ) : (
              <div className="history-list">
                {filteredHistory.map((item, idx) => {
                  const info = getVerdictInfo(item);
                  const isNews = item.kind === "news";
                  const isImage = item.kind === "media" || item.kind === "news_image";

                  return (
                    <div
                      className="history-card-item"
                      key={`${item.id || item.timestamp}-${idx}`}
                      onClick={() => setSelectedScan(item)}
                    >
                      <div className="history-card-icon-col">
                        <div className={`history-kind-badge ${item.kind || "text"}`}>
                          {isNews ? (
                            <Newspaper size={13} />
                          ) : isImage ? (
                            <FileImage size={13} />
                          ) : (
                            <FileText size={13} />
                          )}
                        </div>
                      </div>

                      <div className="history-card-content">
                        <div className="history-card-title-row">
                          <span className="history-card-title" title={item.title}>
                            {item.title || "Scan"}
                          </span>
                          <span className={`verdict-badge ${info.tone}`}>
                            {info.label}
                          </span>
                        </div>

                        <div className="history-card-meta-row">
                          <span className="history-time">
                            <Clock size={10} style={{ marginRight: 3, verticalAlign: "middle" }} />
                            {formatTimestamp(item.timestamp)}
                          </span>
                          {item.result?.confidence !== undefined && (
                            <span className="history-confidence">
                              {item.result.confidence}% confidence
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="history-card-arrow">
                        <ChevronRight size={14} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {/* ════════════════════════════════════════════════════════════════════
            TAB 2: DASHBOARD & METRICS
            ════════════════════════════════════════════════════════════════════ */}
        {activeTab === "dashboard" && (
          <section className="view-enter dashboard-shell">
            {/* Quick Metrics Grid */}
            <div className="metrics-grid">
              <div className="metric-box">
                <span className="metric-label">Total Scans</span>
                <strong className="metric-val">{stats.total}</strong>
                <span className="metric-sub">Across all tabs</span>
              </div>

              <div className="metric-box green">
                <span className="metric-label">Authentic</span>
                <strong className="metric-val">{stats.authentic}</strong>
                <span className="metric-sub">{stats.authenticPct}% of scans</span>
              </div>

              <div className="metric-box red">
                <span className="metric-label">Flagged / AI</span>
                <strong className="metric-val">{stats.aiOrFake}</strong>
                <span className="metric-sub">{stats.aiOrFakePct}% of scans</span>
              </div>
            </div>

            {/* Launch Web Dashboard Callout */}
            <div className="dashboard-cta-card">
              <div className="dashboard-cta-head">
                <div className="dashboard-cta-brand">
                  <Sparkles size={16} style={{ color: "var(--accent)" }} />
                  <strong>VeriFai Full Analytics</strong>
                </div>
                <span className="cta-pill">Web App</span>
              </div>
              <p className="dashboard-cta-desc">
                Access your forensic logs, batch verification tools, and deep learning neural telemetry.
              </p>
              <a
                href={DASHBOARD_URL}
                target="_blank"
                rel="noreferrer"
                className="btn-primary dashboard-link-btn"
              >
                Open Full Web Dashboard <ExternalLink size={13} style={{ marginLeft: 6 }} />
              </a>
            </div>

            {/* System Status & ML Engine Info */}
            <div className="card" style={{ padding: 14 }}>
              <div className="card-title-row" style={{ marginBottom: 8 }}>
                <h3 className="card-title" style={{ fontSize: 12.5 }}>
                  <ShieldCheck size={14} /> Engine &amp; Model Status
                </h3>
                <span className="card-meta">Local Node</span>
              </div>

              <div className="engine-status-list">
                <div className="engine-row">
                  <div className="engine-name-col">
                    <span className="engine-dot live" />
                    <strong>Text Detector</strong>
                  </div>
                  <span className="engine-model-tag">XLM-RoBERTa (v4)</span>
                </div>

                <div className="engine-row">
                  <div className="engine-name-col">
                    <span className="engine-dot live" />
                    <strong>Philippine Fact-Check</strong>
                  </div>
                  <span className="engine-model-tag">Vera Files &amp; Rappler</span>
                </div>

                <div className="engine-row">
                  <div className="engine-name-col">
                    <span className="engine-dot live" />
                    <strong>Visual Forensics</strong>
                  </div>
                  <span className="engine-model-tag">Gemini Vision OCR</span>
                </div>

                <div className="engine-row">
                  <div className="engine-name-col">
                    <span className={`engine-dot ${backendOnline ? "live" : "offline"}`} />
                    <strong>Backend Server</strong>
                  </div>
                  <span className="engine-model-tag">http://localhost:8000</span>
                </div>
              </div>
            </div>

            {/* User Account / Session Profile */}
            <div className="card" style={{ padding: 14 }}>
              <div className="card-title-row" style={{ marginBottom: 6 }}>
                <h3 className="card-title" style={{ fontSize: 12.5 }}>
                  <User size={14} /> Account Status
                </h3>
                <span className="card-meta">{user ? "Active" : "Guest"}</span>
              </div>

              {user ? (
                <div className="user-profile-block">
                  <div className="user-avatar-shell">
                    {user.name ? user.name.slice(0, 2).toUpperCase() : "VF"}
                  </div>
                  <div className="user-profile-details">
                    <strong>{user.name || "VeriFai Member"}</strong>
                    <span>{user.email}</span>
                  </div>
                  <button className="btn-secondary" onClick={handleLogout} style={{ height: 28, fontSize: 11 }}>
                    Sign Out
                  </button>
                </div>
              ) : (
                <div className="guest-profile-block">
                  <p>You are using VeriFai in guest mode. Sign in to sync your scans with the web dashboard.</p>
                  <button className="btn-secondary" onClick={() => setShowAuthModal(true)} style={{ width: "100%", height: 32 }}>
                    <Lock size={12} style={{ marginRight: 6 }} /> Sign In to VeriFai
                  </button>
                </div>
              )}
            </div>

            {/* On-Page Workflow Guide */}
            <div className="shortcuts-guide-card">
              <div className="guide-head">
                <MousePointer2 size={13} style={{ color: "var(--accent)" }} />
                <span>How to Verify on Any Webpage:</span>
              </div>
              <ul className="guide-steps">
                <li>
                  <strong>Highlight Text:</strong> Select 20+ characters anywhere on any site &rarr; Click the floating <strong>"Analyze"</strong> pill.
                </li>
                <li>
                  <strong>Image Cut:</strong> Press <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd> &rarr; Drag a box across any graphic &rarr; Click <strong>"Analyze"</strong>.
                </li>
              </ul>
            </div>
          </section>
        )}
      </main>

      {/* ── Scan Detail Modal (Opened from History Item) ── */}
      {selectedScan && (
        <div className="modal-backdrop" onClick={() => setSelectedScan(null)}>
          <div className="modal-window" role="dialog" aria-modal="true" aria-label="Verification details" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title-wrap">
                <span className="modal-badge-kind">{selectedScan.kind?.toUpperCase() || "SCAN"}</span>
                <h3>Scan Detail</h3>
              </div>
              <button
                className="modal-close-x"
                onClick={() => setSelectedScan(null)}
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>

            <div className="modal-scroll-body">
              {/* Verdict Header */}
              <div className="detail-verdict-banner">
                <span className={`verdict-badge ${getVerdictInfo(selectedScan).tone}`} style={{ fontSize: 11.5, padding: "4px 10px" }}>
                  {getVerdictInfo(selectedScan).label}
                </span>
                {typeof selectedScan.result?.confidence === "number" && (
                  <span className="detail-conf-stat">
                    {selectedScan.result.confidence}% confidence
                  </span>
                )}
              </div>

              {/* Title / Snippet */}
              <div className="detail-field">
                <span className="detail-field-label">Scanned Content</span>
                <p className="detail-field-snippet">{selectedScan.title}</p>
              </div>

              {/* Model Explanation */}
              <div className="detail-field">
                <span className="detail-field-label">Analysis Summary</span>
                <p className="detail-field-desc">
                  {selectedScan.result?.explanation ||
                    selectedScan.result?.summary ||
                    selectedScan.result?.reasoningSummary ||
                    selectedScan.result?.scoreInterpretation ||
                    "No additional summary provided."}
                </p>
              </div>

              {/* Text Dual Bars */}
              {selectedScan.kind === "text" && selectedScan.result && (
                <div className="score-track-block" style={{ margin: "10px 0" }}>
                  <div className="score-track-item">
                    <div className="score-track-head">
                      <span>AI Writing Likelihood</span>
                      <strong>{selectedScan.result.aiProbability ?? selectedScan.result.confidence}%</strong>
                    </div>
                    <div className="score-bar">
                      <div
                        className="score-fill ai"
                        style={{ width: `${selectedScan.result.aiProbability ?? selectedScan.result.confidence}%` }}
                      />
                    </div>
                  </div>
                  <div className="score-track-item">
                    <div className="score-track-head">
                      <span>Human Writing Likelihood</span>
                      <strong>{selectedScan.result.humanProbability ?? 100 - selectedScan.result.confidence}%</strong>
                    </div>
                    <div className="score-bar">
                      <div
                        className="score-fill human"
                        style={{ width: `${selectedScan.result.humanProbability ?? 100 - selectedScan.result.confidence}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Signals */}
              {selectedScan.result?.signals && selectedScan.result.signals.length > 0 && (
                <div className="signals-block" style={{ margin: "10px 0" }}>
                  <div className="signals-label">Detected Signals</div>
                  <div className="signals-list">
                    {selectedScan.result.signals.map((sig) => (
                      <span className="signal-tag" key={sig}>{sig}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Closest Story */}
              {selectedScan.result?.closestStory?.found && (
                <div className="closest-story-card" style={{ margin: "10px 0" }}>
                  <div className="closest-story-copy">
                    <small>CLOSEST VERIFIED REPORT</small>
                    <strong>{selectedScan.result.closestStory.title}</strong>
                    {selectedScan.result.closestStory.url && (
                      <a
                        href={selectedScan.result.closestStory.url}
                        target="_blank"
                        rel="noreferrer"
                        className="story-link"
                      >
                        Read Report <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* Timestamp & Telemetry */}
              <div className="detail-telemetry">
                <span>{selectedScan.result?.details?.model || "VeriFai Backend"}</span>
                <span>{formatTimestamp(selectedScan.timestamp)}</span>
              </div>
            </div>

            <div className="modal-foot">
              <button className="btn-secondary" onClick={handleCopyScan} style={{ height: 32 }}>
                <Copy size={12} style={{ marginRight: 5 }} />
                {copiedDetail ? "Copied!" : "Copy Summary"}
              </button>
              <button className="btn-primary" onClick={() => setSelectedScan(null)} style={{ height: 32 }}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Sign In Modal ── */}
      {showAuthModal && (
        <div className="modal-backdrop" onClick={() => setShowAuthModal(false)}>
          <div className="modal-window" role="dialog" aria-modal="true" aria-label="Sign in to Verif.ai" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Sign In to VeriFai</h3>
              <button
                className="modal-close-x"
                onClick={() => setShowAuthModal(false)}
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>
            <form className="modal-form" onSubmit={handleLogin}>
              {authError && <div className="form-error">{authError}</div>}
              <div className="form-group">
                <label htmlFor="auth-email">Email Address</label>
                <input
                  id="auth-email" autoComplete="email" type="email"
                  className="form-input"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  placeholder="name@example.com"
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="auth-password">Password</label>
                <input
                  id="auth-password" autoComplete="current-password" type="password"
                  className="form-input"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                />
              </div>
              <button type="submit" className="btn-primary" disabled={isLoggingIn} style={{ marginTop: 6 }}>
                {isLoggingIn ? "Signing In…" : "Sign In to VeriFai"}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* ── Footer ── */}
      <footer className="popup-footer">
        <span>Verif.ai · Verify with context</span>
        <a
          href={DASHBOARD_URL}
          target="_blank"
          rel="noreferrer"
          className="footer-link"
        >
          Web Dashboard <ExternalLink size={10} style={{ marginLeft: 2, verticalAlign: "middle" }} />
        </a>
      </footer>
    </div>
  );
}
