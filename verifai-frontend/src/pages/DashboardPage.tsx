import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Check,
  Clipboard,
  Clock3,
  Download,
  FileAudio,
  FileImage,
  FileText,
  FileVideo,
  History,
  Info,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Save,
  Menu,
  Plus,
  Trash2,
  Upload,
  User,
  X,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { logoutUser, type AuthUser } from "@/services/auth";

type ScanKind = "media" | "text";

type ScanResult = {
  id: string;
  kind: ScanKind;
  name: string;
  createdAt: Date;
  classification: string;
  confidence: number;
};

const MAX_FILE_SIZE = 50 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/", "video/", "audio/"];

function readStoredUser(): AuthUser | null {
  try {
    const value = localStorage.getItem("verifai_user");
    return value ? (JSON.parse(value) as AuthUser) : null;
  } catch {
    return null;
  }
}

function fileIcon(file: File) {
  if (file.type.startsWith("video/")) return <FileVideo size={18} />;
  if (file.type.startsWith("audio/")) return <FileAudio size={18} />;
  return <FileImage size={18} />;
}

function formatBytes(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function fileKey(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

function createMockHistory(): ScanResult[] {
  const samples: Array<[number, ScanKind, string, string, number]> = [
    [0, "text", "Community announcement draft", "Likely AI-generated", 76],
    [0, "media", "event-poster.jpg", "Likely authentic", 84],
    [1, "text", "Product description", "Review recommended", 62],
    [1, "media", "news-clip.mp4", "Review recommended", 68],
    [1, "text", "Scholarship application essay", "Likely human-written", 81],
    [2, "media", "profile-photo.png", "Likely authentic", 88],
    [3, "text", "Social media caption", "Likely AI-generated", 73],
    [3, "text", "Customer support response", "Review recommended", 59],
    [5, "media", "interview-audio.mp3", "Likely authentic", 79],
    [5, "text", "Article introduction", "Likely AI-generated", 71],
    [5, "media", "marketplace-listing.webp", "Review recommended", 65],
    [6, "text", "Public advisory message", "Likely human-written", 86],
  ];

  return samples.map(([daysAgo, kind, name, classification, confidence], index) => {
    const createdAt = new Date();
    createdAt.setDate(createdAt.getDate() - daysAgo);
    createdAt.setHours(15 - (index % 6), 10, 0, 0);
    return {
      id: `VF-${(8241 - index * 137).toString(16).toUpperCase()}`,
      kind,
      name,
      createdAt,
      classification,
      confidence,
    };
  });
}

function formatScanDate(date: Date) {
  const scanDate = new Date(date);
  const today = new Date();
  scanDate.setHours(0, 0, 0, 0);
  today.setHours(0, 0, 0, 0);
  const dayDifference = Math.round((today.getTime() - scanDate.getTime()) / 86_400_000);
  if (dayDifference === 0) return "Today";
  if (dayDifference === 1) return "Yesterday";
  return scanDate.toLocaleDateString("en-US", { weekday: "short" });
}

export function DashboardPage() {
  const [user, setUser] = useState(readStoredUser);
  const [profileName, setProfileName] = useState(() => readStoredUser()?.name || "");
  const [profileMessage, setProfileMessage] = useState("");
  const [downloaded, setDownloaded] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState<ScanKind | null>(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [history, setHistory] = useState<ScanResult[]>(createMockHistory);
  const fileInput = useRef<HTMLInputElement>(null);
  const previewUrls = useRef(new Map<string, string>());
  const navigate = useNavigate();
  const location = useLocation();
  const reduceMotion = useReducedMotion();
  const view = location.pathname.endsWith("/text-analyzer")
    ? "text"
    : location.pathname.endsWith("/media-analyzer")
      ? "media"
      : location.pathname.endsWith("/download-extension")
        ? "extension"
        : location.pathname.endsWith("/profile")
          ? "profile"
    : location.pathname.endsWith("/history")
      ? "history"
      : "overview";

  useEffect(() => {
    document.title =
      view === "overview"
        ? "Dashboard | VeriFai"
        : view === "text"
          ? "Text Analyzer | VeriFai"
          : view === "media"
            ? "Media Analyzer | VeriFai"
            : view === "extension"
              ? "Download Extension | VeriFai"
              : view === "profile"
                ? "Profile Settings | VeriFai"
          : "Scan history | VeriFai";
    return () => {
      document.title = "VeriFai — Digital Content Authenticity Analysis";
    };
  }, [view]);

  useEffect(() => {
    if (!scanning) return;
    setProgress(8);
    const progressTimer = window.setInterval(() => {
      setProgress((current) => Math.min(current + Math.ceil(Math.random() * 13), 92));
    }, 260);
    const resultTimer = window.setTimeout(() => {
      const nextResult: ScanResult = {
        id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
        kind: scanning,
        name:
          scanning === "media"
            ? files.length === 1
              ? files[0].name
              : `${files.length} media files`
            : text.trim().slice(0, 54) + (text.trim().length > 54 ? "…" : ""),
        createdAt: new Date(),
        classification: scanning === "text" ? "Likely AI-generated" : "Review recommended",
        confidence: scanning === "text" ? 72 : 68,
      };
      setProgress(100);
      setResult(nextResult);
      setHistory((current) => [nextResult, ...current].slice(0, 20));
      window.setTimeout(() => setScanning(null), 180);
    }, 1900);
    return () => {
      window.clearInterval(progressTimer);
      window.clearTimeout(resultTimer);
    };
  }, [scanning, files, text]);

  useEffect(() => {
    const urls = previewUrls.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  const addFiles = (incoming: File[]) => {
    setError("");
    const nextFile = incoming[0];
    if (!nextFile) return;
    const invalid =
      !ACCEPTED_TYPES.some((accepted) => nextFile.type.startsWith(accepted)) ||
      nextFile.size > MAX_FILE_SIZE;
    if (invalid) {
      setError(
        nextFile.size > MAX_FILE_SIZE
          ? `${nextFile.name} is larger than 50 MB.`
          : `${nextFile.name} is not a supported media file.`,
      );
      return;
    }
    previewUrls.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrls.current.clear();
    const key = fileKey(nextFile);
    if (nextFile.type.startsWith("image/") || nextFile.type.startsWith("video/")) {
      previewUrls.current.set(key, URL.createObjectURL(nextFile));
    }
    setFiles([nextFile]);
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  };

  const startScan = (kind: ScanKind) => {
    setError("");
    if (kind === "media" && files.length === 0) {
      setError("Add at least one image, video, or audio file to continue.");
      return;
    }
    if (kind === "text" && text.trim().length < 20) {
      setError("Paste at least 20 characters for a useful text analysis.");
      return;
    }
    setResult(null);
    setScanning(kind);
  };

  const pasteText = async () => {
    try {
      const clipboardText = await navigator.clipboard.readText();
      setText(clipboardText.slice(0, 10_000));
      setError("");
    } catch {
      setError("Clipboard access was blocked. Use Ctrl+V or paste from the text menu.");
    }
  };

  const signOut = async () => {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  };

  const initials = (user?.name || user?.email || "Guest")
    .split(/[\s@]+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  const firstName = user?.name?.split(" ")[0] || "there";
  const textScanCount = history.filter((item) => item.kind === "text").length;
  const mediaScanCount = history.filter((item) => item.kind === "media").length;
  const weeklyScans = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - (6 - index));
    const count = history.filter((item) => {
      const scanDate = new Date(item.createdAt);
      scanDate.setHours(0, 0, 0, 0);
      return scanDate.getTime() === date.getTime();
    }).length;
    return {
      label: date.toLocaleDateString("en-US", { weekday: "short" }),
      count,
      isToday: index === 6,
    };
  });
  const weeklyMaximum = Math.max(1, ...weeklyScans.map((day) => day.count));

  const goTo = (path: string) => {
    setSidebarOpen(false);
    navigate(path);
  };

  const clearMediaFiles = () => {
    previewUrls.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrls.current.clear();
    setFiles([]);
  };

  const removeMediaFile = (file: File) => {
    const key = fileKey(file);
    const url = previewUrls.current.get(key);
    if (url) URL.revokeObjectURL(url);
    previewUrls.current.delete(key);
    setFiles((current) => current.filter((item) => item !== file));
  };

  const downloadExtension = () => {
    const previewPackage = [
      "VeriFai Browser Extension — Preview Package",
      "",
      "This is a mock download for the VeriFai dashboard prototype.",
      "A production browser extension package will replace this file.",
    ].join("\n");
    const url = URL.createObjectURL(new Blob([previewPackage], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "verifai-extension-preview.txt";
    link.click();
    URL.revokeObjectURL(url);
    setDownloaded(true);
  };

  const saveProfile = () => {
    if (!user || !profileName.trim()) return;
    const updatedUser = { ...user, name: profileName.trim() };
    localStorage.setItem("verifai_user", JSON.stringify(updatedUser));
    setUser(updatedUser);
    setProfileMessage("Profile name saved.");
  };

  return (
    <div className="dashboard-shell dashboard-layout">
      <AnimatePresence>
        {sidebarOpen && (
          <motion.button
            className="mobile-sidebar-backdrop"
            type="button"
            aria-label="Close navigation"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>
      <aside className={`dashboard-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-head">
          <Link className="brand dashboard-brand" to="/" aria-label="VeriFai home">
            <span className="brand-mark" aria-hidden="true"><i /><i /></span>
            <span>VeriFai</span>
          </Link>
          <button className="sidebar-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        <nav className="sidebar-nav" aria-label="Dashboard navigation">
          <p>Workspace</p>
          <button className={view === "overview" ? "active" : ""} type="button" onClick={() => goTo("/dashboard")}>
            <LayoutDashboard size={17} /><span>Overview</span>
          </button>
          <button className={view === "text" ? "active" : ""} type="button" onClick={() => goTo("/dashboard/text-analyzer")}>
            <FileText size={17} /><span>Text Analyzer</span>
          </button>
          <button className={view === "media" ? "active" : ""} type="button" onClick={() => goTo("/dashboard/media-analyzer")}>
            <FileImage size={17} /><span>Media Analyzer</span>
          </button>
          <p className="sidebar-section-label">Tools</p>
          <button className={view === "extension" ? "active" : ""} type="button" onClick={() => goTo("/dashboard/download-extension")}>
            <Download size={17} /><span>Download Extension</span>
          </button>
          <p className="sidebar-section-label">Account</p>
          <button className={view === "history" ? "active" : ""} type="button" onClick={() => goTo("/dashboard/history")}>
            <History size={17} /><span>Scan history</span>
          </button>
          <button className={view === "profile" ? "active" : ""} type="button" onClick={() => goTo("/dashboard/profile")}>
            <User size={17} /><span>Profile Settings</span>
          </button>
        </nav>
        <div className="sidebar-account">
          <span className="sidebar-avatar">{initials}</span>
          <div><strong>{user?.name || "My account"}</strong><span>{user?.email || "Guest user"}</span></div>
          <button type="button" onClick={signOut} aria-label="Sign out"><LogOut size={16} /></button>
        </div>
      </aside>

      <div className="dashboard-workspace">
        <header className="dashboard-topbar">
          <button className="dashboard-menu-button" type="button" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}>
            <Menu size={19} />
          </button>
          <div><span>{view === "overview" ? "Overview" : view === "text" ? "Text Analyzer" : view === "media" ? "Media Analyzer" : view === "extension" ? "Download Extension" : view === "profile" ? "Profile Settings" : "Scan history"}</span></div>
          {(view === "overview" || view === "history") && (
            <button className="new-scan-link" type="button" onClick={() => goTo("/dashboard/text-analyzer")}>
              <Plus size={16} /> New text scan
            </button>
          )}
        </header>

        <main className="dashboard-main">
          {view === "overview" && (
            <motion.div className="dashboard-overview" initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <section className="overview-welcome compact-welcome">
                <div><h1>Welcome back, {firstName}.</h1><p>Here is a summary of your analysis activity.</p></div>
              </section>
              <section className="overview-summary" aria-label="Session summary">
                <div><span>Total analyses</span><strong>{history.length}</strong><small>This week</small></div>
                <div><span>Text scans</span><strong>{textScanCount}</strong><small>This week</small></div>
                <div><span>Media scans</span><strong>{mediaScanCount}</strong><small>This week</small></div>
              </section>
              <section className="overview-insights-grid">
                <article className="weekly-chart-card">
                  <div className="weekly-chart-heading">
                    <div><p className="kicker">WEEKLY ACTIVITY</p><h2>Scans this week</h2></div>
                    <span><strong>{history.length}</strong> total scans</span>
                  </div>
                  <div className="weekly-chart" role="img" aria-label={`Weekly scan activity. ${history.length} total scans this week.`}>
                    <div className="chart-grid-lines" aria-hidden="true"><i /><i /><i /><i /></div>
                    {weeklyScans.map((day) => (
                      <div className={`weekly-bar-column ${day.isToday ? "today" : ""}`} key={day.label}>
                        <div className="weekly-bar-value"><span>{day.count || ""}</span><i style={{ height: day.count ? `${Math.max(12, (day.count / weeklyMaximum) * 100)}%` : "3px" }} /></div>
                        <strong>{day.label}</strong>
                      </div>
                    ))}
                  </div>
                </article>
                <article className="scan-history">
                  <div className="lower-heading"><div><p className="kicker">RECENT ACTIVITY</p><h2>Latest scans</h2></div><button type="button" onClick={() => goTo("/dashboard/history")}>View history</button></div>
                  {history.length === 0 ? <div className="empty-history"><Clock3 size={21} /><div><strong>No scans yet</strong><p>Start an analysis and it will appear here.</p></div></div> : (
                    <div className="history-list">{history.slice(0, 3).map((item) => <div className="history-item" key={item.id}><span>{item.kind === "text" ? <FileText size={17} /> : <FileImage size={17} />}</span><div><strong>{item.name}</strong><small>{item.id} · {formatScanDate(item.createdAt)}</small></div><b>{item.confidence}%</b></div>)}</div>
                  )}
                </article>
              </section>
            </motion.div>
          )}

          {(view === "text" || view === "media") && (<>
        <section className="analyzer-page-heading" id="new-analysis">
          <h1>{view === "text" ? "Text Analyzer" : "Media Analyzer"}</h1>
          <p>{view === "text" ? "Paste written content to check for signals associated with AI-generated writing." : "Upload an image, video, or audio file to check for AI-generated or manipulated signals."}</p>
        </section>

        {error && (
          <div className="dashboard-alert" role="alert">
            <Info size={17} /><span>{error}</span>
            <button type="button" onClick={() => setError("")} aria-label="Dismiss message"><X size={16} /></button>
          </div>
        )}

        <section className={`analysis-options single-analyzer ${view === "text" ? "text-analyzer-grid" : view === "media" ? "media-analyzer-grid" : ""}`} aria-label="Content analyzer">
          {view === "media" && (
          <article className="analysis-card media-analysis-card">
            <div className="analysis-card-heading">
              <span className="analysis-number">01</span>
              <div>
                <h2>Upload multimedia</h2>
                <p>Analyze images, videos, or audio from your device.</p>
              </div>
            </div>
            <input
              ref={fileInput}
              className="visually-hidden"
              type="file"
              accept="image/*,video/*,audio/*"
              onChange={handleFileChange}
            />
            <div
              className={`media-dropzone ${dragging ? "dragging" : ""} ${files.length ? "has-files" : ""}`}
              onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
              }}
              onDrop={handleDrop}
            >
              {files.length === 0 ? (
                <>
                  <span className="dropzone-icon"><Upload size={22} /></span>
                  <strong>Drop your files here</strong>
                  <p>or choose files from your device</p>
                  <button className="button secondary" type="button" onClick={() => fileInput.current?.click()}>Browse files</button>
                  <small>JPG, PNG, WEBP, MP4, MOV, MP3 or WAV · maximum 50 MB</small>
                </>
              ) : (
                <div className="dropzone-preview-content">
                  <div className="dropzone-preview-heading">
                    <strong>{files.length} {files.length === 1 ? "file" : "files"} ready</strong>
                    <button type="button" onClick={clearMediaFiles}>Clear all</button>
                  </div>
                  <div className={`dropzone-preview-grid ${files.length === 1 ? "single" : ""}`}>
                    {files.map((file) => (
                      <figure key={fileKey(file)}>
                        <div className="dropzone-media">
                          {file.type.startsWith("image/") && previewUrls.current.get(fileKey(file)) ? (
                            <img src={previewUrls.current.get(fileKey(file))} alt={`Preview of ${file.name}`} />
                          ) : file.type.startsWith("video/") && previewUrls.current.get(fileKey(file)) ? (
                            <video src={previewUrls.current.get(fileKey(file))} muted preload="metadata" aria-label={`Preview of ${file.name}`} />
                          ) : (
                            <span>{fileIcon(file)}</span>
                          )}
                          <button type="button" aria-label={`Remove ${file.name}`} onClick={() => removeMediaFile(file)}><Trash2 size={15} /></button>
                        </div>
                        <figcaption><strong>{file.name}</strong><small>{formatBytes(file.size)}</small></figcaption>
                      </figure>
                    ))}
                  </div>
                  <small>Drop another file here to replace this one.</small>
                </div>
              )}
            </div>
            <button className="button primary analysis-action" type="button" disabled={scanning !== null} onClick={() => startScan("media")}>
              {scanning === "media" ? <><LoaderCircle className="spin" size={17} /> Analyzing media…</> : <>Analyze media <ArrowRight size={17} /></>}
            </button>
          </article>
          )}

          {view === "media" && (
            <aside className="text-result-card media-result-card" aria-live="polite">
              <div className="text-result-heading">
                <div><p>ANALYSIS RESULT</p><h2>Media assessment</h2></div>
                {result?.kind === "media" && !scanning && <span>Complete</span>}
              </div>

              {!scanning && (!result || result.kind !== "media") && (
                <div className="text-result-empty">
                  <span><FileImage size={20} /></span>
                  <strong>Your result will appear here</strong>
                  <p>Drag media into the upload area and select “Analyze media” to see its estimated authenticity.</p>
                </div>
              )}

              {scanning === "media" && (
                <div className="text-result-loading">
                  <LoaderCircle className="spin" size={20} />
                  <div><strong>Inspecting the media…</strong><span>Checking details, repeated patterns, and file signals.</span></div>
                  <b>{progress}%</b>
                  <span className="result-loading-track"><i style={{ width: `${progress}%` }} /></span>
                </div>
              )}

              {!scanning && result?.kind === "media" && (
                <motion.div className="text-result-content" initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="plain-verdict">
                    <span>OVERALL ASSESSMENT</span>
                    <h3>Likely AI-generated or altered</h3>
                    <p>The uploaded media contains more signals commonly found in generated or manipulated files.</p>
                  </div>
                  <div className="likelihood-bars">
                    <div>
                      <div><span>AI-generated or altered</span><strong>{result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="ai-bar" style={{ width: `${result.confidence}%` }} /></span>
                    </div>
                    <div>
                      <div><span>Likely authentic</span><strong>{100 - result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="human-bar" style={{ width: `${100 - result.confidence}%` }} /></span>
                    </div>
                  </div>
                  <div className="plain-evidence">
                    <h3>Why VeriFai reached this result</h3>
                    <ul>
                      <li><Check size={15} /><span><strong>Unusual fine details</strong>Some small areas do not look as naturally formed as the rest of the media.</span></li>
                      <li><Check size={15} /><span><strong>Repeated visual patterns</strong>Similar textures appear where natural variation is normally expected.</span></li>
                      <li><Check size={15} /><span><strong>File-level signals</strong>The file contains processing patterns often left by generation or editing tools.</span></li>
                    </ul>
                  </div>
                  <p className="result-caution"><Info size={14} /> This is an estimate, not proof. Check the original source before making a decision.</p>
                </motion.div>
              )}
            </aside>
          )}

          {view === "text" && (
          <article className="analysis-card text-analysis-card">
            <div className="analysis-card-heading">
              <span className="analysis-number">02</span>
              <div>
                <h2>Paste text</h2>
                <p>Check an article, message, caption, or written passage.</p>
              </div>
            </div>
            <div className="text-input-shell">
              <div className="text-input-toolbar">
                <span><FileText size={15} /> Text to analyze</span>
                <div>
                  <button type="button" onClick={pasteText}><Clipboard size={14} /> Paste</button>
                  {text && <button type="button" onClick={() => setText("")}><X size={14} /> Clear</button>}
                </div>
              </div>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value.slice(0, 10_000))}
                placeholder="Paste the text you want to check here…"
                aria-label="Text to analyze"
              />
              <div className="text-input-meta">
                <span>English, Filipino, and Taglish supported</span>
                <span>{text.length.toLocaleString()} / 10,000</span>
              </div>
            </div>
            <div className="text-guidance"><Info size={16} /><p><strong>For a clearer assessment,</strong> include at least a few complete sentences. Short phrases may not contain enough signals.</p></div>
            <button className="button primary analysis-action" type="button" disabled={scanning !== null} onClick={() => startScan("text")}>
              {scanning === "text" ? <><LoaderCircle className="spin" size={17} /> Analyzing text…</> : <>Analyze text <ArrowRight size={17} /></>}
            </button>
          </article>
          )}

          {view === "text" && (
            <aside className="text-result-card" aria-live="polite">
              <div className="text-result-heading">
                <div><p>ANALYSIS RESULT</p><h2>Writing assessment</h2></div>
                {result?.kind === "text" && !scanning && <span>Complete</span>}
              </div>

              {!scanning && (!result || result.kind !== "text") && (
                <div className="text-result-empty">
                  <span><FileText size={20} /></span>
                  <strong>Your result will appear here</strong>
                  <p>Paste your text and select “Analyze text” to see the estimated human and AI likelihood.</p>
                </div>
              )}

              {scanning === "text" && (
                <div className="text-result-loading">
                  <LoaderCircle className="spin" size={20} />
                  <div><strong>Reading the writing patterns…</strong><span>Comparing sentence structure, wording, and consistency.</span></div>
                  <b>{progress}%</b>
                  <span className="result-loading-track"><i style={{ width: `${progress}%` }} /></span>
                </div>
              )}

              {!scanning && result?.kind === "text" && (
                <motion.div className="text-result-content" initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="plain-verdict">
                    <span>OVERALL ASSESSMENT</span>
                    <h3>{result.classification}</h3>
                    <p>The writing contains more patterns commonly found in AI-generated text.</p>
                  </div>
                  <div className="likelihood-bars">
                    <div>
                      <div><span>Artificially generated</span><strong>{result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="ai-bar" style={{ width: `${result.confidence}%` }} /></span>
                    </div>
                    <div>
                      <div><span>Written by a human</span><strong>{100 - result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="human-bar" style={{ width: `${100 - result.confidence}%` }} /></span>
                    </div>
                  </div>
                  <div className="plain-evidence">
                    <h3>Why VeriFai reached this result</h3>
                    <ul>
                      <li><Check size={15} /><span><strong>Very even sentence structure</strong>Many sentences are built in a similar way, which is common in generated writing.</span></li>
                      <li><Check size={15} /><span><strong>Predictable word choices</strong>Several phrases follow patterns that AI writing tools often repeat.</span></li>
                      <li><Check size={15} /><span><strong>Consistent tone throughout</strong>The writing style changes less than it usually does in natural human writing.</span></li>
                    </ul>
                  </div>
                  <p className="result-caution"><Info size={14} /> This is an estimate, not proof. Review the source and context before making a decision.</p>
                </motion.div>
              )}
            </aside>
          )}
        </section>

        </>)}

        {view === "extension" && (
          <section className="dashboard-tool-page">
            <div className="tool-page-heading">
              <h1>Download Extension</h1>
              <p>Use VeriFai from your browser while reading content online.</p>
            </div>
            <div className="extension-download-card">
              <div className="extension-product">
                <span className="extension-product-mark"><span className="brand-mark" aria-hidden="true"><i /><i /></span></span>
                <div><small>BROWSER EXTENSION</small><h2>VeriFai for Chrome and Edge</h2><p>Select text or media on a webpage and send it to your VeriFai workspace for analysis.</p></div>
              </div>
              <div className="extension-download-action">
                <span>Preview package · Version 0.1</span>
                <button className="button primary large" type="button" onClick={downloadExtension}><Download size={17} /> Download Extension</button>
                {downloaded && <p role="status"><Check size={14} /> Preview download started.</p>}
              </div>
            </div>
            <div className="extension-install-grid">
              <article><span>01</span><div><h3>Download the package</h3><p>Use the button above to download the current mock extension package.</p></div></article>
              <article><span>02</span><div><h3>Open browser extensions</h3><p>Visit your browser’s extension management page and enable developer mode.</p></div></article>
              <article><span>03</span><div><h3>Load and pin VeriFai</h3><p>Load the unpacked extension, then pin it for quick access while browsing.</p></div></article>
            </div>
            <p className="extension-preview-note"><Info size={15} /> This is a prototype download page. The production extension package will replace the preview file.</p>
          </section>
        )}

        {view === "profile" && (
          <section className="dashboard-tool-page profile-page">
            <div className="tool-page-heading">
              <h1>Profile Settings</h1>
              <p>Manage the personal information shown in your VeriFai workspace.</p>
            </div>
            <form className="profile-settings-card" onSubmit={(event) => { event.preventDefault(); saveProfile(); }}>
              <div className="profile-card-heading">
                <span className="sidebar-avatar">{initials}</span>
                <div><h2>Personal information</h2><p>Update your display name and review your account email.</p></div>
              </div>
              <div className="profile-form-grid">
                <label>
                  <span>Display name</span>
                  <input value={profileName} onChange={(event) => { setProfileName(event.target.value); setProfileMessage(""); }} maxLength={50} required />
                </label>
                <label>
                  <span>Email address</span>
                  <input value={user?.email || ""} readOnly aria-readonly="true" />
                  <small>Email changes are not available yet.</small>
                </label>
              </div>
              <div className="profile-form-actions">
                {profileMessage && <p role="status"><Check size={14} /> {profileMessage}</p>}
                <button className="button primary" type="submit"><Save size={16} /> Save changes</button>
              </div>
            </form>
          </section>
        )}

        {view === "history" && (
        <section className="dashboard-history-view">
          <div className="history-page-heading">
            <div><p className="kicker">ACTIVITY</p><h1>Scan history</h1><p>Review your recent content analyses.</p></div>
            <button className="button primary" type="button" onClick={() => goTo("/dashboard/text-analyzer")}><Plus size={16} /> New text scan</button>
          </div>
          <div className="dashboard-lower-grid history-list-only">
          <article className="scan-history" id="scan-history">
            <div className="lower-heading"><div><p className="kicker">YOUR ACTIVITY</p><h2>Recent scans</h2></div>{history.length > 0 && <span>{history.length} this week</span>}</div>
            {history.length === 0 ? (
              <div className="empty-history"><Clock3 size={21} /><div><strong>No scans yet</strong><p>Your completed analyses will appear here for quick reference.</p></div></div>
            ) : (
              <div className="history-list">
                {history.map((item) => (
                  <div className="history-item" key={item.id}>
                    <span>{item.kind === "text" ? <FileText size={17} /> : <FileImage size={17} />}</span>
                    <div><strong>{item.name}</strong><small>{item.id} · {formatScanDate(item.createdAt)}</small></div>
                    <b>{item.confidence}%</b>
                  </div>
                ))}
              </div>
            )}
          </article>
          </div>
        </section>
        )}
      </main>

      <footer className="dashboard-footer">
        <span>© 2026 VeriFai</span>
        <span>Built for more careful sharing online.</span>
      </footer>
      </div>
    </div>
  );
}
