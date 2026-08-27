import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Check,
  Clipboard,
  Clock3,
  Download,
  ExternalLink,
  FileAudio,
  FileImage,
  FileText,
  FileVideo,
  History,
  ImageUp,
  Info,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Newspaper,
  Save,
  Menu,
  Plus,
  ScanText,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  User,
  X,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { logoutUser, type AuthUser } from "@/services/auth";

type ScanKind = "media" | "text" | "news";

type ScanResult = {
  id: string;
  kind: ScanKind;
  name: string;
  createdAt: Date;
  classification: string;
  confidence: number;
  aiConfidence?: number;
  humanConfidence?: number;
  chunksAnalyzed?: number;
  newsVerification?: NewsVerificationResponse;
};

type TextDetectionResponse = {
  classification: "Likely AI-generated" | "Likely human-written" | "Review recommended";
  confidence: number;
  ai_probability: number;
  human_probability: number;
  chunks_analyzed: number;
};

type NewsVerdict =
  | "VERIFIED"
  | "LIKELY_TRUE"
  | "MISLEADING"
  | "UNVERIFIED"
  | "LIKELY_FALSE"
  | "FALSE";

type NewsEvidenceItem = {
  title: string;
  publisher: string;
  url: string;
  domain: string;
  published_date: string | null;
  image_url: string;
  relationship: "SUPPORTS" | "CONTRADICTS" | "RELATED" | "DEBUNKS";
  similarity: number;
  evidence_score: number;
  source_tier: number;
  explanation: string;
};

type NewsVerificationResponse = {
  status: "SUCCESS" | "SEARCH_UNAVAILABLE";
  original_text: string;
  cleaned_text: string;
  search_text: string;
  detected: {
    entities: string[];
    keywords: string[];
    event_categories: string[];
    dates: string[];
  };
  verdict: NewsVerdict;
  confidence: number;
  explanation: string;
  evidence: {
    supporting: NewsEvidenceItem[];
    contradicting: NewsEvidenceItem[];
    related: NewsEvidenceItem[];
    debunks: NewsEvidenceItem[];
  };
  closest_real_story: {
    found: boolean;
    title: string;
    publisher: string;
    url: string;
    date: string;
    similarity: number;
    explanation: string;
    image_url: string;
  };
  search: {
    queries: string[];
    providers_used: string[];
    outlet_domains_searched: string[];
    total_results: number;
    articles_scraped: number;
  };
};

const MAX_FILE_SIZE = 50 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/", "video/", "audio/"];
const MAX_NEWS_IMAGE_SIZE = 10 * 1024 * 1024;

function readStoredUser(): AuthUser | null {
  try {
    const value = sessionStorage.getItem("verifai_user");
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

function analysisErrorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const message = detail
      .map((item) => (typeof item === "object" && item && "message" in item ? item.message : ""))
      .filter(Boolean)
      .join(" ");
    if (message) return message;
  }
  return "Analysis could not be completed. Please try again.";
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

function formatNewsVerdict(verdict: NewsVerdict) {
  const labels: Record<NewsVerdict, string> = {
    VERIFIED: "Real news",
    LIKELY_TRUE: "Likely real",
    MISLEADING: "Misleading",
    UNVERIFIED: "Not enough information",
    LIKELY_FALSE: "Likely fake",
    FALSE: "Fake news",
  };
  return labels[verdict];
}

function newsVerdictTone(verdict: NewsVerdict) {
  if (verdict === "VERIFIED" || verdict === "LIKELY_TRUE") return "real";
  if (verdict === "UNVERIFIED") return "uncertain";
  if (verdict === "MISLEADING") return "warning";
  return "fake";
}

function newsVerdictHeading(result: NewsVerificationResponse) {
  if (result.status === "SEARCH_UNAVAILABLE") {
    return "We could not check this news right now.";
  }
  if (result.verdict === "VERIFIED" || result.verdict === "LIKELY_TRUE") {
    return "This news matches reliable reporting.";
  }
  if (result.verdict === "MISLEADING") return "This news changes important details or context.";
  if (result.verdict === "UNVERIFIED") return "There is not enough information to decide.";
  if (result.verdict === "LIKELY_FALSE") return "This news is likely fake.";
  return "Reliable sources show that this news is fake.";
}

function formatEvidenceRelationship(relationship: NewsEvidenceItem["relationship"]) {
  if (relationship === "SUPPORTS") return "Supports this news";
  if (relationship === "DEBUNKS") return "Fact-check";
  if (relationship === "CONTRADICTS") return "Reports different facts";
  return "Related report";
}

function sourceMonogram(publisher: string) {
  return publisher
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
}

export function DashboardPage() {
  const [user, setUser] = useState(readStoredUser);
  const [profileName, setProfileName] = useState(() => readStoredUser()?.name || "");
  const [profileMessage, setProfileMessage] = useState("");
  const [downloaded, setDownloaded] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [newsText, setNewsText] = useState("");
  const [newsMode, setNewsMode] = useState<"text" | "image">("text");
  const [newsImage, setNewsImage] = useState<File | null>(null);
  const [newsImageUrl, setNewsImageUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState<ScanKind | null>(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [history, setHistory] = useState<ScanResult[]>(createMockHistory);
  const fileInput = useRef<HTMLInputElement>(null);
  const newsFileInput = useRef<HTMLInputElement>(null);
  const previewUrls = useRef(new Map<string, string>());
  const navigate = useNavigate();
  const location = useLocation();
  const reduceMotion = useReducedMotion();
  const view = location.pathname.endsWith("/text-analyzer")
    ? "text"
    : location.pathname.endsWith("/media-analyzer")
      ? "media"
      : location.pathname.endsWith("/fake-news-analyzer")
        ? "news"
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
        ? "Dashboard | Verif.Ai"
        : view === "text"
          ? "Text Analyzer | Verif.Ai"
          : view === "media"
            ? "Media Analyzer | Verif.Ai"
            : view === "news"
              ? "News Checker | Verif.Ai"
            : view === "extension"
              ? "Download Extension | Verif.Ai"
              : view === "profile"
                ? "Profile Settings | Verif.Ai"
          : "Scan history | Verif.Ai";
    return () => {
      document.title = "Verif.Ai — Digital Content Authenticity Analysis";
    };
  }, [view]);

  useEffect(() => {
    if (scanning !== "media") return;
    setProgress(8);
    const progressTimer = window.setInterval(() => {
      setProgress((current) => Math.min(current + Math.ceil(Math.random() * 13), 92));
    }, 260);
    const resultTimer = window.setTimeout(() => {
      const nextResult: ScanResult = {
        id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
        kind: "media",
        name: files.length === 1 ? files[0].name : `${files.length} media files`,
        createdAt: new Date(),
        classification: "Review recommended",
        confidence: 68,
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
  }, [scanning, files]);

  useEffect(() => {
    const urls = previewUrls.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  useEffect(() => {
    return () => {
      if (newsImageUrl) URL.revokeObjectURL(newsImageUrl);
    };
  }, [newsImageUrl]);

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

  const startScan = async (kind: ScanKind) => {
    setError("");
    if (kind === "media" && files.length === 0) {
      setError("Add at least one image, video, or audio file to continue.");
      return;
    }
    if (kind === "text" && text.trim().length < 20) {
      setError("Paste at least 20 characters for a useful text analysis.");
      return;
    }
    if (kind === "news" && newsMode === "text" && newsText.trim().length < 5) {
      setError("Enter at least 5 characters from the news story.");
      return;
    }
    if (kind === "news" && newsMode === "image" && !newsImage) {
      setError("Upload a screenshot or photo containing the news.");
      return;
    }
    if (kind === "news" && newsMode === "image") {
      setError("Image OCR verification is not connected yet. Use Paste text for this release.");
      return;
    }
    setResult(null);
    setScanning(kind);
    if (kind === "media") return;

    setProgress(8);
    const progressTimer = window.setInterval(() => {
      setProgress((current) => Math.min(current + Math.ceil(Math.random() * 8), 92));
    }, 500);
    try {
      let nextResult: ScanResult;
      if (kind === "text") {
        const response = await api.post<TextDetectionResponse>(
          "/detector/text",
          { text: text.trim() },
          { timeout: 120_000 },
        );
        nextResult = {
          id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
          kind: "text",
          name: text.trim().slice(0, 54) + (text.trim().length > 54 ? "…" : ""),
          createdAt: new Date(),
          classification: response.data.classification,
          confidence: Math.round(response.data.confidence * 100),
          aiConfidence: Math.round(response.data.ai_probability * 100),
          humanConfidence: Math.round(response.data.human_probability * 100),
          chunksAnalyzed: response.data.chunks_analyzed,
        };
      } else {
        const response = await api.post<NewsVerificationResponse>(
          "/news/verify",
          { text: newsText.trim() },
          { timeout: 120_000 },
        );
        nextResult = {
          id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
          kind: "news",
          name:
            newsText.trim().slice(0, 54) + (newsText.trim().length > 54 ? "…" : ""),
          createdAt: new Date(),
          classification:
            response.data.status === "SEARCH_UNAVAILABLE"
              ? "Check unavailable"
              : formatNewsVerdict(response.data.verdict),
          confidence: response.data.confidence,
          newsVerification: response.data,
        };
      }
      setProgress(100);
      setResult(nextResult);
      setHistory((current) => [nextResult, ...current].slice(0, 20));
    } catch (requestError) {
      setError(analysisErrorMessage(requestError));
      setProgress(0);
    } finally {
      window.clearInterval(progressTimer);
      setScanning(null);
    }
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

  const pasteNewsText = async () => {
    try {
      const clipboardText = await navigator.clipboard.readText();
      setNewsText(clipboardText.slice(0, 10_000));
      setError("");
    } catch {
      setError("Clipboard access was blocked. Use Ctrl+V or paste from the text menu.");
    }
  };

  const addNewsImage = (file?: File) => {
    setError("");
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > MAX_NEWS_IMAGE_SIZE) {
      setError(
        file.size > MAX_NEWS_IMAGE_SIZE
          ? `${file.name} is larger than 10 MB.`
          : `${file.name} is not a supported image.`,
      );
      return;
    }
    setNewsImage(file);
    setNewsImageUrl(URL.createObjectURL(file));
    setResult(null);
  };

  const clearNewsImage = () => {
    setNewsImage(null);
    setNewsImageUrl("");
    setResult(null);
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
  const newsVerification = result?.kind === "news" ? result.newsVerification : undefined;
  const newsIsReal = newsVerification
    ? newsVerification.verdict === "VERIFIED" || newsVerification.verdict === "LIKELY_TRUE"
    : false;
  const showNewsVerdict = Boolean(
    newsVerification && newsVerification.status !== "SEARCH_UNAVAILABLE",
  );
  const newsEvidence = newsVerification
    ? [
        ...newsVerification.evidence.debunks,
        ...newsVerification.evidence.contradicting,
        ...newsVerification.evidence.supporting,
        ...newsVerification.evidence.related,
      ].slice(0, 6)
    : [];
  const closestRelatedReport = newsVerification
    ? [
        ...newsVerification.evidence.related,
        ...newsVerification.evidence.contradicting,
        ...newsVerification.evidence.debunks,
        ...newsVerification.evidence.supporting,
      ][0]
    : undefined;
  const relatedNews = !newsIsReal && newsVerification
    ? newsVerification.closest_real_story.found
      ? newsVerification.closest_real_story
      : closestRelatedReport
        ? {
            title: closestRelatedReport.title,
            publisher: closestRelatedReport.publisher,
            url: closestRelatedReport.url,
            explanation: closestRelatedReport.explanation,
            image_url: closestRelatedReport.image_url,
          }
        : null
    : null;
  const displayedNewsEvidence = relatedNews
    ? newsEvidence.filter((item) => item.url !== relatedNews.url)
    : newsEvidence;

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
      "Verif.Ai Browser Extension — Preview Package",
      "",
      "This is a mock download for the Verif.Ai dashboard prototype.",
      "A production browser extension package will replace this file.",
    ].join("\n");
    const url = URL.createObjectURL(new Blob([previewPackage], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "verif-ai-extension-preview.txt";
    link.click();
    URL.revokeObjectURL(url);
    setDownloaded(true);
  };

  const saveProfile = () => {
    if (!user || !profileName.trim()) return;
    const updatedUser = { ...user, name: profileName.trim() };
    sessionStorage.setItem("verifai_user", JSON.stringify(updatedUser));
    setUser(updatedUser);
    setProfileMessage("Profile name saved.");
  };

  return (
    <div className={`dashboard-shell dashboard-layout ${view === "news" ? "news-checker-shell" : ""}`}>
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
          <Link className="brand dashboard-brand" to="/" aria-label="Verif.Ai home">
            <span className="brand-mark" aria-hidden="true"><i /><i /></span>
            <span>Verif.Ai</span>
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
          <button className={view === "news" ? "active" : ""} type="button" onClick={() => goTo("/dashboard/fake-news-analyzer")}>
            <Newspaper size={17} /><span>News Checker</span>
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
          <div><span>{view === "overview" ? "Overview" : view === "text" ? "Text Analyzer" : view === "media" ? "Media Analyzer" : view === "news" ? "News Checker" : view === "extension" ? "Download Extension" : view === "profile" ? "Profile Settings" : "Scan history"}</span></div>
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
                    <h3>Why Verif.Ai reached this result</h3>
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
                    <p>
                      {result.classification === "Likely AI-generated"
                        ? "The model found more patterns associated with AI-generated writing."
                        : result.classification === "Likely human-written"
                          ? "The model found more patterns associated with human writing."
                          : "The model found mixed signals, so a manual review is recommended."}
                    </p>
                  </div>
                  <div className="likelihood-bars">
                    <div>
                      <div><span>Artificially generated</span><strong>{result.aiConfidence ?? result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="ai-bar" style={{ width: `${result.aiConfidence ?? result.confidence}%` }} /></span>
                    </div>
                    <div>
                      <div><span>Written by a human</span><strong>{result.humanConfidence ?? 100 - result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="human-bar" style={{ width: `${result.humanConfidence ?? 100 - result.confidence}%` }} /></span>
                    </div>
                  </div>
                  <div className="plain-evidence">
                    <h3>How this result was produced</h3>
                    <ul>
                      <li><Check size={15} /><span><strong>Classifier estimate</strong>The displayed percentages come directly from the trained text model.</span></li>
                      <li><Check size={15} /><span><strong>Full-text coverage</strong>{result.chunksAnalyzed === 1 ? "The text fit in one model window." : `The text was scored across ${result.chunksAnalyzed} overlapping model windows.`}</span></li>
                      <li><Check size={15} /><span><strong>Uncertain results are flagged</strong>Close probabilities produce a review recommendation instead of a forced verdict.</span></li>
                    </ul>
                  </div>
                  <p className="result-caution"><Info size={14} /> This is an estimate, not proof. Review the source and context before making a decision.</p>
                </motion.div>
              )}
            </aside>
          )}
        </section>

        </>)}

        {view === "news" && (
          <>
            <section className="analyzer-page-heading news-checker-intro" id="fake-news-analysis">
              <span>FAKE NEWS ANALYZER</span>
              <h1>Check before you share</h1>
              <p>Paste a story or upload a screenshot. We will compare it with reliable reporting.</p>
            </section>

            {error && (
              <div className="dashboard-alert" role="alert">
                <Info size={17} /><span>{error}</span>
                <button type="button" onClick={() => setError("")} aria-label="Dismiss message"><X size={16} /></button>
              </div>
            )}

            <section className="analysis-options news-analyzer-grid" aria-label="News checker">
              <article className="analysis-card news-analysis-card">
                <div className="analysis-card-heading">
                  <span className="analysis-number">1</span>
                  <div>
                    <h2>Add news to check</h2>
                    <p>Paste the text or upload a clear screenshot of the story.</p>
                  </div>
                </div>

                <div className="news-input-switch" role="tablist" aria-label="News input type">
                  <button
                    className={newsMode === "text" ? "active" : ""}
                    type="button"
                    role="tab"
                    aria-selected={newsMode === "text"}
                    onClick={() => { setNewsMode("text"); setError(""); setResult(null); }}
                  >
                    <FileText size={17} /> Paste text
                  </button>
                  <button
                    className={newsMode === "image" ? "active" : ""}
                    type="button"
                    role="tab"
                    aria-selected={newsMode === "image"}
                    onClick={() => { setNewsMode("image"); setError(""); setResult(null); }}
                  >
                    <ImageUp size={17} /> Upload image
                  </button>
                </div>

                {newsMode === "text" ? (
                  <div className="text-input-shell news-text-input">
                    <div className="text-input-toolbar">
                      <span><Newspaper size={15} /> News text</span>
                      <div>
                        <button type="button" onClick={pasteNewsText}><Clipboard size={14} /> Paste</button>
                        {newsText && <button type="button" onClick={() => { setNewsText(""); setResult(null); }}><X size={14} /> Clear</button>}
                      </div>
                    </div>
                    <textarea
                      value={newsText}
                      onChange={(event) => { setNewsText(event.target.value.slice(0, 10_000)); setResult(null); }}
                      placeholder="Paste or type the news story here..."
                      aria-label="News text to check"
                    />
                    <div className="text-input-meta">
                      <span>English, Filipino, and Taglish supported</span>
                      <span>{newsText.length.toLocaleString()} / 10,000</span>
                    </div>
                  </div>
                ) : (
                  <>
                    <input
                      ref={newsFileInput}
                      className="visually-hidden"
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={(event) => {
                        addNewsImage(event.target.files?.[0]);
                        event.target.value = "";
                      }}
                    />
                    <div
                      className={`media-dropzone news-image-dropzone ${newsImage ? "has-files" : ""}`}
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        addNewsImage(event.dataTransfer.files?.[0]);
                      }}
                    >
                      {!newsImage ? (
                        <>
                          <span className="dropzone-icon"><ScanText size={22} /></span>
                          <strong>Upload a screenshot</strong>
                          <p>We will read the words in the image and check the story.</p>
                          <button className="button secondary" type="button" onClick={() => newsFileInput.current?.click()}>Choose an image</button>
                          <small>JPG, PNG or WEBP · up to 10 MB</small>
                        </>
                      ) : (
                        <div className="news-image-preview">
                          <img src={newsImageUrl} alt={`Preview of ${newsImage.name}`} />
                          <div>
                            <span><ImageUp size={15} /></span>
                            <div><strong>{newsImage.name}</strong><small>{formatBytes(newsImage.size)} · Ready for OCR</small></div>
                            <button type="button" onClick={clearNewsImage} aria-label={`Remove ${newsImage.name}`}><Trash2 size={15} /></button>
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}

                <div className="news-search-note">
                  <Info size={18} />
                  <p><strong>Tip:</strong> Add as much detail as you can, including names, dates, places, and key claims.</p>
                </div>
                <button className="button primary analysis-action" type="button" disabled={scanning !== null} onClick={() => startScan("news")}>
                  {scanning === "news" ? <><LoaderCircle className="spin" size={18} /> Searching Philippine news...</> : <><Search size={18} /> Check this news</>}
                </button>
              </article>

              <aside className="text-result-card news-result-card" aria-live="polite">
                <div className="text-result-heading">
                  <span className="analysis-number">2</span>
                  <div><h2>Results</h2></div>
                </div>

                {!scanning && (!result || result.kind !== "news") && (
                  <div className="text-result-empty">
                    <span><ShieldCheck size={24} /></span>
                    <strong>Your results will appear here</strong>
                    <p>Add a story in step 1, then choose “Check this news.”</p>
                  </div>
                )}

                {scanning === "news" && (
                  <div className="text-result-loading news-result-loading">
                    <LoaderCircle className="spin" size={20} />
                    <div><strong>{newsMode === "image" ? "Extracting text and searching…" : "Searching for matching coverage…"}</strong><span>Checking Philippine news outlets, then weighing source quality and claim details.</span></div>
                    <b>{progress}%</b>
                    <span className="result-loading-track"><i style={{ width: `${progress}%` }} /></span>
                    <ol>
                      <li className={progress > 20 ? "done" : ""}>Understand the main story</li>
                      <li className={progress > 48 ? "done" : ""}>Find independent coverage</li>
                      <li className={progress > 76 ? "done" : ""}>Compare facts and context</li>
                    </ol>
                  </div>
                )}

                {!scanning && result?.kind === "news" && newsVerification && (
                  <motion.div className="news-result-content" initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <div className="news-verdict">
                      <div>
                        {showNewsVerdict && (
                          <span data-news-result={newsVerdictTone(newsVerification.verdict)}>{formatNewsVerdict(newsVerification.verdict)}</span>
                        )}
                        <strong>{showNewsVerdict ? `We're ${newsVerification.confidence}% sure` : "Please try again later"}</strong>
                      </div>
                      <h3>{newsVerdictHeading(newsVerification)}</h3>
                      <p>{newsVerification.explanation}</p>
                    </div>

                    {showNewsVerdict && relatedNews && (
                      <div className="closest-story">
                        <span className="closest-story-media">
                          <Newspaper size={18} />
                          {relatedNews.image_url && (
                            <img
                              src={relatedNews.image_url}
                              alt={`Thumbnail for ${relatedNews.title}`}
                              loading="lazy"
                              referrerPolicy="no-referrer"
                              onError={(event) => { event.currentTarget.hidden = true; }}
                            />
                          )}
                        </span>
                        <div>
                          <small>CLOSEST MATCHING REPORT</small>
                          <h3>{relatedNews.title}</h3>
                          <p>{relatedNews.explanation}</p>
                          <a href={relatedNews.url} target="_blank" rel="noreferrer">
                            Read on {relatedNews.publisher || "the original source"} <ExternalLink size={13} />
                          </a>
                        </div>
                      </div>
                    )}

                    {displayedNewsEvidence.length > 0 && (
                      <div className="source-list">
                        <div className="source-list-heading">
                          <h3>{newsIsReal ? "Reports that confirm it" : "Other reports used for this check"}</h3>
                          <span>{displayedNewsEvidence.length} {displayedNewsEvidence.length === 1 ? "report" : "reports"}</span>
                        </div>
                        {displayedNewsEvidence.map((source) => (
                          <a href={source.url} target="_blank" rel="noreferrer" key={`${source.relationship}-${source.url}`}>
                            <span className="source-monogram">{sourceMonogram(source.publisher)}</span>
                            <div>
                              <strong>{source.publisher} · {formatEvidenceRelationship(source.relationship)}</strong>
                              <p>{source.title}</p>
                            </div>
                            <ExternalLink size={14} />
                          </a>
                        ))}
                      </div>
                    )}

                  </motion.div>
                )}
              </aside>
            </section>
          </>
        )}

        {view === "extension" && (
          <section className="dashboard-tool-page">
            <div className="tool-page-heading">
              <h1>Download Extension</h1>
              <p>Use Verif.Ai from your browser while reading content online.</p>
            </div>
            <div className="extension-download-card">
              <div className="extension-product">
                <span className="extension-product-mark"><span className="brand-mark" aria-hidden="true"><i /><i /></span></span>
                <div><small>BROWSER EXTENSION</small><h2>Verif.Ai for Chrome and Edge</h2><p>Select text or media on a webpage and send it to your Verif.Ai workspace for analysis.</p></div>
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
              <article><span>03</span><div><h3>Load and pin Verif.Ai</h3><p>Load the unpacked extension, then pin it for quick access while browsing.</p></div></article>
            </div>
            <p className="extension-preview-note"><Info size={15} /> This is a prototype download page. The production extension package will replace the preview file.</p>
          </section>
        )}

        {view === "profile" && (
          <section className="dashboard-tool-page profile-page">
            <div className="tool-page-heading">
              <h1>Profile Settings</h1>
              <p>Manage the personal information shown in your Verif.Ai workspace.</p>
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
        <span>© 2026 Verif.Ai</span>
        <span>Built for more careful sharing online.</span>
      </footer>
      </div>
    </div>
  );
}
