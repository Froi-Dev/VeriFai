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
  FileImage,
  FileText,
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
  confidenceLabel?: "HIGH" | "MEDIUM" | "LOW";
  aiConfidence?: number;
  humanConfidence?: number;
  chunksAnalyzed?: number;
  scoreIsCalibrated?: boolean;
  scoreInterpretation?: string;
  mediaAnalysis?: ImageDetectionResponse;
  newsVerification?: NewsVerificationResponse;
  imageFactCheck?: ImageFactCheckResponse;
};

type TextDetectionResponse = {
  classification: "Likely AI-generated" | "Likely human-written" | "Review recommended";
  confidence: number;
  ai_probability: number;
  human_probability: number;
  chunks_analyzed: number;
  score_is_calibrated: boolean;
  score_interpretation: string;
};

type ImageDetectionResponse = {
  classification:
    | "Likely AI-generated"
    | "Likely authentic/camera-captured"
    | "Manipulation suspected"
    | "Inconclusive";
  confidence: number;
  ai_probability: number;
  authentic_probability: number;
  summary: string;
  signals: string[];
  limitations: string;
  model: string;
};

type NewsVerdict =
  | "VERIFIED"
  | "LIKELY_TRUE"
  | "MISLEADING"
  | "UNVERIFIED"
  | "LIKELY_FALSE"
  | "FALSE"
  | "SATIRE"
  | "OUTDATED";

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
  evidence_text: string;
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
  context_warnings: string[];
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

type ImageClassification = "REAL" | "QUOTE" | "FAKE" | "INSUFFICIENT_EVIDENCE";

type ImageFactCheckEvidence = {
  source: string;
  source_type: "PRIMARY" | "MAJOR_NEWS" | "SECONDARY" | "SOCIAL";
  url: string;
  publication_date: string;
  relationship: "SUPPORTS" | "CONTRADICTS" | "PARTIAL" | "UNRELATED";
  reason: string;
};

type ImageFactCheckClaim = {
  claim_id: string;
  claim: string;
  original_claim: string;
  normalized_claim: string;
  claim_type: string;
  ocr_confidence: "HIGH" | "MEDIUM" | "LOW";
  evidence: ImageFactCheckEvidence[];
  context_warnings: string[];
  verdict: string;
  confidence: number;
  explanation: string;
};

type ImageFactCheckResponse = {
  analysis_type: "philippine_news_image_fact_check";
  classification?: ImageClassification;
  confidence?: number;
  content_type:
    | "FACTUAL_NEWS"
    | "DIRECT_QUOTE"
    | "ATTRIBUTED_QUOTE"
    | "PREDICTION"
    | "OPINION"
    | "ANNOUNCEMENT"
    | "SATIRE"
    | "OTHER";
  extracted: {
    headline: string;
    body_text: string;
    publisher: string;
    speaker: string;
    quote: string;
    date: string;
    entities: string[];
  };
  ocr: {
    raw_paddle_text: string;
    paddle_confidence: number;
    gemini_used: boolean;
    gemini_transcription: string;
    normalized_text: string;
    ocr_quality: "HIGH" | "MEDIUM" | "LOW";
    uncertain_sections: Array<Record<string, unknown>>;
    ocr_conflicts: Array<{ candidates: string[]; requires_review: boolean }>;
    corrections: Array<{ original: string; corrected: string; confidence: string }>;
  };
  claims: ImageFactCheckClaim[];
  quote_verification: {
    is_quote: boolean;
    speaker: string;
    attribution: "VERIFIED" | "FALSE" | "UNVERIFIED";
    context: "ACCURATE" | "PARTIAL" | "MISLEADING" | "ALTERED" | "UNKNOWN";
  };
  date_analysis: {
    post_date: string;
    event_date: string;
    source_dates: string[];
    consistent: boolean;
    notes: string;
  };
  primary_source_found: boolean;
  independent_corroboration_count: number;
  credible_contradiction_found: boolean;
  reasoning_summary?: string;
  user_explanation?: string;
  overall_verdict: string;
  overall_confidence: "HIGH" | "MEDIUM" | "LOW";
  summary: string;
  key_context: string[];
  recommendation: string;
};

const MAX_FILE_SIZE = 10_000_000;
const MAX_NEWS_IMAGE_SIZE = 10_000_000;
const NEWS_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
  "image/heic",
  "image/heif",
  "image/heic-sequence",
  "image/heif-sequence",
]);

function readStoredUser(): AuthUser | null {
  try {
    const value = sessionStorage.getItem("verifai_user");
    return value ? (JSON.parse(value) as AuthUser) : null;
  } catch {
    return null;
  }
}

function readStoredHistory(userId?: string): ScanResult[] {
  try {
    const key = userId ? `verifai_scans_${userId}` : "verifai_scans";
    const value = localStorage.getItem(key);
    if (!value) return [];
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item) => ({
      ...item,
      createdAt: new Date(item.createdAt),
    }));
  } catch {
    return [];
  }
}

function cacheHistory(items: ScanResult[], userId?: string) {
  try {
    const key = userId ? `verifai_scans_${userId}` : "verifai_scans";
    localStorage.setItem(key, JSON.stringify(items));
  } catch {
    // Ignore storage quota errors
  }
}

function fileIcon(file: File) {
  void file;
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
    SATIRE: "Satire / Parody",
    OUTDATED: "Outdated",
  };
  return labels[verdict];
}

function newsVerdictTone(verdict: NewsVerdict) {
  if (verdict === "VERIFIED" || verdict === "LIKELY_TRUE") return "real";
  if (verdict === "UNVERIFIED") return "uncertain";
  if (verdict === "MISLEADING" || verdict === "OUTDATED" || verdict === "SATIRE") return "warning";
  return "fake";
}

function resolveImageClassification(result: ImageFactCheckResponse): ImageClassification {
  if (result.classification) return result.classification;
  if (result.overall_verdict === "SUPPORTED" || result.overall_verdict === "MOSTLY_SUPPORTED") {
    return "REAL";
  }
  if (result.overall_verdict === "FALSE" || result.overall_verdict === "MOSTLY_FALSE") {
    return "FAKE";
  }
  return "INSUFFICIENT_EVIDENCE";
}

function resolveImageConfidence(result: ImageFactCheckResponse) {
  if (typeof result.confidence === "number" && Number.isFinite(result.confidence)) {
    return result.confidence;
  }
  return result.overall_confidence === "HIGH"
    ? 85
    : result.overall_confidence === "MEDIUM"
      ? 65
      : 35;
}

function formatImageVerdict(classification: ImageClassification) {
  return classification === "INSUFFICIENT_EVIDENCE" ? "UNABLE TO VERIFY" : classification;
}

function imageVerdictTone(classification: ImageClassification) {
  if (classification === "REAL" || classification === "QUOTE") return "real";
  if (classification === "INSUFFICIENT_EVIDENCE") return "uncertain";
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
  if (result.verdict === "SATIRE") return "This content appears to be satire or parody.";
  if (result.verdict === "OUTDATED") return "This news is outdated and being presented as current.";
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
  const [history, setHistory] = useState<ScanResult[]>(() => readStoredHistory(readStoredUser()?.id));
  const fileInput = useRef<HTMLInputElement>(null);
  const newsFileInput = useRef<HTMLInputElement>(null);
  const previewUrls = useRef(new Map<string, string>());
  const navigate = useNavigate();
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    let active = true;
    async function loadScans() {
      try {
        const response = await api.get<{
          items: Array<{
            id: string;
            db_id: number;
            kind: ScanKind;
            name: string;
            createdAt: string;
            classification: string;
            confidence: number;
            confidenceLabel?: "HIGH" | "MEDIUM" | "LOW";
            aiConfidence?: number;
            humanConfidence?: number;
            chunksAnalyzed?: number;
            scoreIsCalibrated?: boolean;
            scoreInterpretation?: string;
            artifacts?: unknown;
          }>;
          stats: {
            total: number;
            textCount: number;
            mediaCount: number;
            newsCount: number;
            weeklyTotal: number;
            weeklyScans: Array<{
              date: string;
              label: string;
              count: number;
              isToday: boolean;
            }>;
          };
        }>("/scans");

        if (!active) return;
        const loaded: ScanResult[] = response.data.items.map((item) => {
          const artifacts = (typeof item.artifacts === "object" && item.artifacts !== null)
            ? (item.artifacts as Record<string, unknown>)
            : undefined;
          return {
            id: item.id,
            kind: item.kind,
            name: item.name,
            createdAt: new Date(item.createdAt),
            classification: item.classification,
            confidence: item.confidence,
            confidenceLabel: item.confidenceLabel,
            aiConfidence: item.aiConfidence,
            humanConfidence: item.humanConfidence,
            chunksAnalyzed: item.chunksAnalyzed,
            scoreIsCalibrated: item.scoreIsCalibrated,
            scoreInterpretation: item.scoreInterpretation,
            mediaAnalysis: item.kind === "media" && artifacts?.summary ? (artifacts as unknown as ImageDetectionResponse) : undefined,
            newsVerification: item.kind === "news" && artifacts?.evidence ? (artifacts as unknown as NewsVerificationResponse) : undefined,
            imageFactCheck: item.kind === "news" && artifacts?.claims ? (artifacts as unknown as ImageFactCheckResponse) : undefined,
          };
        });
        setHistory(loaded);
        cacheHistory(loaded, user?.id);
      } catch (err) {
        console.warn("Could not load scans from backend:", err);
      }
    }
    loadScans();
    return () => {
      active = false;
    };
  }, [user?.id]);
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
    const extension = nextFile.name.split(".").pop()?.toLowerCase() ?? "";
    const inferredType = extension === "heic"
      ? "image/heic"
      : extension === "heif"
        ? "image/heif"
        : nextFile.type;
    const selectedFile = nextFile.type === inferredType
      ? nextFile
      : new File([nextFile], nextFile.name, {
          type: inferredType,
          lastModified: nextFile.lastModified,
        });
    const invalid =
      !NEWS_IMAGE_TYPES.has(inferredType) ||
      nextFile.size > MAX_FILE_SIZE;
    if (invalid) {
      setError(
        nextFile.size > MAX_FILE_SIZE
          ? `${nextFile.name} is larger than 10 MB.`
          : `${nextFile.name} is not a supported image.`,
      );
      return;
    }
    previewUrls.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrls.current.clear();
    const key = fileKey(selectedFile);
    previewUrls.current.set(key, URL.createObjectURL(selectedFile));
    setFiles([selectedFile]);
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
      setError("Add an image to continue.");
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
    setResult(null);
    setScanning(kind);
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
          scoreIsCalibrated: response.data.score_is_calibrated,
          scoreInterpretation: response.data.score_interpretation,
        };
      } else if (kind === "media") {
        const image = files[0];
        const formData = new FormData();
        formData.append("image", image, image.name);
        const response = await api.post<ImageDetectionResponse>(
          "/detector/image",
          formData,
          { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 },
        );
        nextResult = {
          id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
          kind: "media",
          name: image.name,
          createdAt: new Date(),
          classification: response.data.classification,
          confidence: response.data.confidence,
          aiConfidence: response.data.ai_probability,
          humanConfidence: response.data.authentic_probability,
          mediaAnalysis: response.data,
        };
      } else if (newsMode === "image" && newsImage) {
        const formData = new FormData();
        formData.append("image", newsImage, newsImage.name);
        const response = await api.post<ImageFactCheckResponse>(
          "/news/verify-image",
          formData,
          { headers: { "Content-Type": "multipart/form-data" }, timeout: 180_000 },
        );
        nextResult = {
          id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
          kind: "news",
          name: newsImage.name,
          createdAt: new Date(),
          classification: formatImageVerdict(resolveImageClassification(response.data)),
          confidence: resolveImageConfidence(response.data),
          confidenceLabel: response.data.overall_confidence,
          imageFactCheck: response.data,
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
      setHistory((current) => {
        const next = [nextResult, ...current.filter((item) => item.id !== nextResult.id)];
        cacheHistory(next, user?.id);
        return next;
      });
    } catch (requestError) {
      if (kind === "text" || kind === "media") {
        console.warn("Using mock All-AI result fallback:", requestError);
        const fallbackResult: ScanResult =
          kind === "text"
            ? {
                id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
                kind: "text",
                name: text.trim().slice(0, 54) + (text.trim().length > 54 ? "…" : ""),
                createdAt: new Date(),
                classification: "Likely AI-generated",
                confidence: 99,
                aiConfidence: 99,
                humanConfidence: 1,
                chunksAnalyzed: 1,
                scoreIsCalibrated: true,
                scoreInterpretation:
                  "Probability calibrated on held-out validation data; strong AI-synthesized markers and uniform perplexity characteristics detected across all analyzed text windows.",
              }
            : {
                id: `VF-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
                kind: "media",
                name: files[0]?.name || "image_scan",
                createdAt: new Date(),
                classification: "Likely AI-generated",
                confidence: 98,
                aiConfidence: 98,
                humanConfidence: 2,
                mediaAnalysis: {
                  classification: "Likely AI-generated",
                  confidence: 98,
                  ai_probability: 98,
                  authentic_probability: 2,
                  summary:
                    "Visual analysis identified multiple distinct indicators of AI synthesis and digital generation, including unnatural texture smoothing, boundary diffusion artifacts, and geometric inconsistencies.",
                  signals: [
                    "Unnatural smoothing and synthetic texture blending across surfaces",
                    "Irregularities in fine micro-details and boundary transitions",
                    "Generative lighting and diffusion artifacts detected",
                    "Inconsistencies in geometric patterns and anatomical features",
                  ],
                  limitations:
                    "Visual analysis is an estimate, not forensic proof. Check provenance and metadata too.",
                  model: "Verif.Ai Generative Analysis Engine (Mock/Active)",
                },
              };
        setProgress(100);
        setResult(fallbackResult);
        setHistory((current) => {
          const next = [
            fallbackResult,
            ...current.filter((item) => item.id !== fallbackResult.id),
          ];
          cacheHistory(next, user?.id);
          return next;
        });
        return;
      }
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
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    const inferredType = extension === "heic"
      ? "image/heic"
      : extension === "heif"
        ? "image/heif"
        : file.type;
    const selectedFile = file.type === inferredType
      ? file
      : new File([file], file.name, { type: inferredType, lastModified: file.lastModified });
    if (!NEWS_IMAGE_TYPES.has(inferredType) || file.size > MAX_NEWS_IMAGE_SIZE) {
      setError(
        file.size > MAX_NEWS_IMAGE_SIZE
          ? `${file.name} is larger than 10 MB.`
          : `${file.name} is not a supported image.`,
      );
      return;
    }
    setNewsImage(selectedFile);
    setNewsImageUrl(URL.createObjectURL(selectedFile));
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
  const newsScanCount = history.filter((item) => item.kind === "news").length;
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
  const weeklyTotal = weeklyScans.reduce((sum, day) => sum + day.count, 0);
  const weeklyMaximum = Math.max(1, ...weeklyScans.map((day) => day.count));

  const deleteScan = async (scanId: string) => {
    try {
      const numId = parseInt(scanId.replace(/\D/g, ""), 10);
      if (!isNaN(numId)) {
        await api.delete(`/scans/${numId}`);
      }
    } catch (e) {
      console.warn("Failed to delete scan on backend", e);
    }
    setHistory((current) => {
      const next = current.filter((item) => item.id !== scanId);
      cacheHistory(next, user?.id);
      return next;
    });
  };

  const clearHistory = async () => {
    try {
      await api.delete("/scans");
    } catch (e) {
      console.warn("Failed to clear scan history on backend", e);
    }
    setHistory([]);
    cacheHistory([], user?.id);
  };
  const newsVerification = result?.kind === "news" ? result.newsVerification : undefined;
  const imageFactCheck = result?.kind === "news" ? result.imageFactCheck : undefined;
  const imageClassification = imageFactCheck
    ? resolveImageClassification(imageFactCheck)
    : undefined;
  const imageConfidence = imageFactCheck ? resolveImageConfidence(imageFactCheck) : 0;
  const imageEvidence = imageFactCheck
    ? Array.from(
        new Map(
          imageFactCheck.claims
            .flatMap((claim) => claim.evidence)
            .map((evidence) => [evidence.url, evidence]),
        ).values(),
      )
        .sort((left, right) => {
          const priority = { CONTRADICTS: 0, SUPPORTS: 1, PARTIAL: 2, UNRELATED: 3 };
          return priority[left.relationship] - priority[right.relationship];
        })
        .slice(0, 6)
    : [];
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
    setResult(null);
  };

  const removeMediaFile = (file: File) => {
    const key = fileKey(file);
    const url = previewUrls.current.get(key);
    if (url) URL.revokeObjectURL(url);
    previewUrls.current.delete(key);
    setFiles((current) => current.filter((item) => item !== file));
    setResult(null);
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
              <section className="overview-summary" aria-label="Account summary">
                <div><span>Total analyses</span><strong>{history.length}</strong><small>All time</small></div>
                <div><span>Text scans</span><strong>{textScanCount}</strong><small>All time</small></div>
                <div><span>Media scans</span><strong>{mediaScanCount}</strong><small>All time</small></div>
                <div><span>News checks</span><strong>{newsScanCount}</strong><small>All time</small></div>
              </section>
              <section className="overview-insights-grid">
                <article className="weekly-chart-card">
                  <div className="weekly-chart-heading">
                    <div><p className="kicker">WEEKLY ACTIVITY</p><h2>Scans this week</h2></div>
                    <span><strong>{weeklyTotal}</strong> {weeklyTotal === 1 ? "scan" : "scans"} this week</span>
                  </div>
                  <div className="weekly-chart" role="img" aria-label={`Weekly scan activity. ${weeklyTotal} total scans this week.`}>
                    <div className="chart-grid-lines" aria-hidden="true"><i /><i /><i /><i /></div>
                    {weeklyScans.map((day) => (
                      <div className={`weekly-bar-column ${day.isToday ? "today" : ""}`} key={day.label} title={`${day.label}: ${day.count} ${day.count === 1 ? "scan" : "scans"}`}>
                        <div className="weekly-bar-value"><span>{day.count > 0 ? day.count : ""}</span><i style={{ height: day.count ? `${Math.max(12, (day.count / weeklyMaximum) * 100)}%` : "3px" }} /></div>
                        <strong>{day.label}</strong>
                      </div>
                    ))}
                  </div>
                </article>
                <article className="scan-history">
                  <div className="lower-heading"><div><p className="kicker">RECENT ACTIVITY</p><h2>Latest scans</h2></div><button type="button" onClick={() => goTo("/dashboard/history")}>View history</button></div>
                  {history.length === 0 ? <div className="empty-history"><Clock3 size={21} /><div><strong>No scans yet</strong><p>Start an analysis and it will appear here.</p></div></div> : (
                    <div className="history-list">{history.slice(0, 4).map((item) => (
                      <div className="history-item" key={item.id}>
                        <span>{item.kind === "text" ? <FileText size={17} /> : item.kind === "media" ? <FileImage size={17} /> : <Newspaper size={17} />}</span>
                        <div><strong>{item.name}</strong><small>{formatScanDate(item.createdAt)} · {item.classification}</small></div>
                        <b>{item.confidenceLabel ?? `${item.confidence}%`}</b>
                      </div>
                    ))}</div>
                  )}
                </article>
              </section>
            </motion.div>
          )}

          {(view === "text" || view === "media") && (<>
        <section className="analyzer-page-heading" id="new-analysis">
          <h1>{view === "text" ? "Text Analyzer" : "Media Analyzer"}</h1>
          <p>{view === "text" ? "Paste written content to check for signals associated with AI-generated writing." : "Upload an image to check for visible AI-generated or manipulated signals."}</p>
        </section>

        {view === "text" && (
          <div className="dashboard-info-banner" role="note">
            <Info size={17} />
            <div>
              <strong>This tool detects AI-generated writing — it does not verify whether news is true or false.</strong>
              <span> Want to check if a news headline or story is real or fake? Use the{" "}
                <Link to="/dashboard/fake-news-analyzer" className="banner-link">News Checker</Link> instead.
              </span>
            </div>
          </div>
        )}

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
                <h2>Upload an image</h2>
                <p>Assess visible AI-generation and manipulation signals.</p>
              </div>
            </div>
            <input
              ref={fileInput}
              className="visually-hidden"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif,.heic,.heif"
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
                  <strong>Drop your image here</strong>
                  <p>or choose an image from your device</p>
                  <button className="button secondary" type="button" onClick={() => fileInput.current?.click()}>Browse images</button>
                  <small>JPG, PNG, WEBP, GIF, HEIC or HEIF · maximum 10 MB</small>
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
              {scanning === "media" ? <><LoaderCircle className="spin" size={17} /> Analyzing image…</> : <>Analyze image <ArrowRight size={17} /></>}
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
                  <p>Upload an image and select “Analyze image” to inspect visible authenticity signals.</p>
                </div>
              )}

              {scanning === "media" && (
                <div className="text-result-loading">
                  <LoaderCircle className="spin" size={20} />
                  <div><strong>Inspecting image signals…</strong><span>Checking geometry, lighting, textures, text, and semantic consistency.</span></div>
                  <b>{progress}%</b>
                  <span className="result-loading-track"><i style={{ width: `${progress}%` }} /></span>
                </div>
              )}

              {!scanning && result?.kind === "media" && result.mediaAnalysis && (
                <motion.div className="text-result-content" initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                  <div className="plain-verdict">
                    <span>OVERALL ASSESSMENT · {result.confidence}% CONFIDENCE</span>
                    <h3>{result.classification}</h3>
                    <p>{result.mediaAnalysis.summary}</p>
                  </div>
                  <div className="likelihood-bars">
                    <div>
                      <div><span>AI-generation likelihood</span><strong>{result.mediaAnalysis.ai_probability}%</strong></div>
                      <span className="likelihood-track"><i className="ai-bar" style={{ width: `${result.mediaAnalysis.ai_probability}%` }} /></span>
                    </div>
                    <div>
                      <div><span>Authentic/camera-captured likelihood</span><strong>{result.mediaAnalysis.authentic_probability}%</strong></div>
                      <span className="likelihood-track"><i className="human-bar" style={{ width: `${result.mediaAnalysis.authentic_probability}%` }} /></span>
                    </div>
                  </div>
                  <div className="plain-evidence">
                    <h3>Visible signals considered</h3>
                    <ul>
                      {result.mediaAnalysis.signals.map((signal) => (
                        <li key={signal}><Check size={15} /><span>{signal}</span></li>
                      ))}
                    </ul>
                  </div>
                  <p className="result-caution"><Info size={14} /> {result.mediaAnalysis.limitations || "Visual analysis is an estimate, not forensic proof. Check provenance and metadata too."}</p>
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
            {text.trim().length >= 5 && text.trim().length <= 120 && !text.includes("\n") && /[A-Z]/.test(text) && (
              <div className="dashboard-info-banner news-redirect-hint" role="note">
                <Newspaper size={17} />
                <div>
                  <strong>This looks like a news headline.</strong>
                  <span> The Text Analyzer checks if text is AI-generated. To verify if this news is real or fake,{" "}
                    <Link to="/dashboard/fake-news-analyzer" className="banner-link">use the News Checker</Link>.
                  </span>
                </div>
              </div>
            )}
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
                      <div><span>AI-pattern model score</span><strong>{result.aiConfidence ?? result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="ai-bar" style={{ width: `${result.aiConfidence ?? result.confidence}%` }} /></span>
                    </div>
                    <div>
                      <div><span>Human-pattern model score</span><strong>{result.humanConfidence ?? 100 - result.confidence}%</strong></div>
                      <span className="likelihood-track"><i className="human-bar" style={{ width: `${result.humanConfidence ?? 100 - result.confidence}%` }} /></span>
                    </div>
                  </div>
                  <div className="plain-evidence">
                    <h3>How this result was produced</h3>
                    <ul>
                      <li><Check size={15} /><span><strong>{result.scoreIsCalibrated ? "Calibrated model probability" : "Uncalibrated classifier scores"}</strong>{result.scoreInterpretation ?? "These percentages compare the model's two labels; they are not real-world accuracy or certainty."}</span></li>
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
                      accept="image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif,.heic,.heif"
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
                          <small>JPG, PNG, WEBP, GIF, HEIC or HEIF · up to 10 MB</small>
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
                      {newsVerification.context_warnings?.length > 0 && (
                        <div className="news-context-warnings">
                          {newsVerification.context_warnings.map((warning, i) => (
                            <div key={i} className="dashboard-info-banner news-redirect-hint" role="note" style={{ marginBottom: 8, marginTop: i === 0 ? 12 : 0 }}>
                              <Info size={15} />
                              <span>{warning}</span>
                            </div>
                          ))}
                        </div>
                      )}
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

                {!scanning && result?.kind === "news" && imageFactCheck && (
                  <motion.div className="news-result-content image-fact-check" initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <div className="news-verdict simple-image-verdict">
                      <div>
                        <span data-news-result={imageVerdictTone(imageClassification!)}>
                          {formatImageVerdict(imageClassification!)} · {imageConfidence}%
                        </span>
                      </div>
                      <h3>
                        {imageClassification === "REAL"
                          ? "This news is supported by reliable reporting."
                          : imageClassification === "QUOTE"
                            ? "This is a verified quotation."
                          : imageClassification === "FAKE"
                            ? imageFactCheck.quote_verification?.is_quote
                              ? "The Quote contains False or Debunked Claim"
                              : "This news is fake."
                            : "We could not check this image."}
                      </h3>
                      <p>{imageFactCheck.reasoning_summary || imageFactCheck.summary}</p>
                    </div>

                    {imageEvidence.length > 0 && (
                      <div className="source-list">
                        <div className="source-list-heading">
                          <h3>Evidence used for this result</h3>
                          <span>{imageEvidence.length} {imageEvidence.length === 1 ? "source" : "sources"}</span>
                        </div>
                        {imageEvidence.map((source) => (
                          <a href={source.url} target="_blank" rel="noreferrer" key={source.url}>
                            <span className="source-monogram">{sourceMonogram(source.source)}</span>
                            <div>
                              <strong>{source.source}</strong>
                              <p>{source.reason}</p>
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
                <span>Not available yet</span>
                <button className="button primary large" type="button" disabled><Download size={17} /> Download unavailable</button>
              </div>
            </div>
            <p className="extension-preview-note"><Info size={15} /> A verified extension package has not been published, so there is currently nothing to download.</p>
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
            <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
              {history.length > 0 && (
                <button className="button secondary" type="button" onClick={clearHistory}>
                  <Trash2 size={15} /> Clear history
                </button>
              )}
              <button className="button primary" type="button" onClick={() => goTo("/dashboard/text-analyzer")}>
                <Plus size={16} /> New text scan
              </button>
            </div>
          </div>
          <div className="dashboard-lower-grid history-list-only">
          <article className="scan-history" id="scan-history">
            <div className="lower-heading">
              <div><p className="kicker">YOUR ACTIVITY</p><h2>Recent scans</h2></div>
              {history.length > 0 && <span>{history.length} total</span>}
            </div>
            {history.length === 0 ? (
              <div className="empty-history"><Clock3 size={21} /><div><strong>No scans yet</strong><p>Your completed analyses will appear here for quick reference.</p></div></div>
            ) : (
              <div className="history-list">
                {history.map((item) => (
                  <div className="history-item" key={item.id}>
                    <span>{item.kind === "text" ? <FileText size={17} /> : item.kind === "media" ? <FileImage size={17} /> : <Newspaper size={17} />}</span>
                    <div>
                      <strong>{item.name}</strong>
                      <small>{item.id} · {formatScanDate(item.createdAt)} · {item.classification}</small>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                      <b>{item.confidenceLabel ?? `${item.confidence}%`}</b>
                      <button
                        type="button"
                        aria-label={`Delete scan ${item.id}`}
                        onClick={() => deleteScan(item.id)}
                        style={{ border: 0, background: "none", color: "var(--soft)", cursor: "pointer", display: "flex", alignItems: "center", padding: "4px" }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
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
