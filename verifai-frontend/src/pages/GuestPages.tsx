import { T } from "@/i18n/LanguageContext";
import { useLanguage } from "@/i18n/useLanguage";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import axios from "axios";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  FileImage,
  FileText,
  ImageUp,
  Info,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { TrialLayout, trialScanners } from "@/components/TrialLayout";
import { TextFileUpload } from "@/components/TextFileUpload";
import { api } from "@/lib/api";
import { acceptConsent, getQuota, guestError, guestHeaders, type Quota, type Scanner } from "@/services/guest";
import {
  TextScanResultView,
  MediaScanResultView,
  NewsScanResultView,
  type TextScanData,
  type MediaScanData,
  type NewsVerificationData,
} from "@/components/ScanResults";
import "./guest.css";

const labels: Record<Scanner, string> = {
  text: "AI Text Scanner",
  image: "AI Image Scanner",
  news: "Fake News / Fact Checker",
};

function formatBytes(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function GuestConsentPage() {
  const { t } = useLanguage();
  const [accepted, setAccepted] = useState([false, false]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    if (sessionStorage.getItem("verifai_user")) {
      navigate("/dashboard", { replace: true });
    }
  }, [navigate]);

  return (
    <TrialLayout page="consent">
      <header className="tool-page-heading">
        <h1><T>{"Subukan ng Libre"}</T></h1>
        <p><T>{"Text, image, at fact checks. Walang account na kailangan."}</T></p>
      </header>
      <div className="trial-onboarding-grid">
        <section className="trial-panel">
          <div className="analysis-card-heading">
            <span className="analysis-number"><ShieldCheck size={19} /></span>
            <div>
              <h2><T>{"Bago tayo magsimula"}</T></h2>
              <p><T>{"Basahin at tanggapin ang dalawang pahintulot upang magpatuloy."}</T></p>
            </div>
          </div>
          <form onSubmit={async event => {
            event.preventDefault();
            if (!accepted.every(Boolean) || busy) return;
            setBusy(true); setError("");
            try {
              await acceptConsent();
              navigate("/guest/scanner");
            } catch (e) {
              setError(guestError(e));
            } finally {
              setBusy(false);
            }
          }}>
            {[
              [
                "Functional & Trial Tracking Cookies",
                "We use essential session cookies and a persistent trial token to remember your progress and enforce your rolling 24-hour scan quota across the web and extension without requiring an account.",
              ],
              [
                "Terms of Service & Device Consent",
                "I agree to the Verif.AI Terms of Service and consent to anonymous device identity hashing (IP and browser characteristics) solely to prevent quota abuse. Content submitted is evaluated for verification purposes only.",
              ],
            ].map(([title, description], index) => (
              <label className={`trial-consent ${accepted[index] ? "is-accepted" : ""}`} key={title}>
                <input
                  type="checkbox"
                  required
                  checked={accepted[index]}
                  disabled={busy}
                  onChange={e => setAccepted(values => values.map((v, i) => i === index ? e.target.checked : v))}
                />
                <span>
                  <strong>{title}</strong>
                  <small>{description}</small>
                  <span className="trial-consent-choice"><T>{"Accept / Tanggapin"}</T></span>
                </span>
              </label>
            ))}
            {error && <p className="trial-error" role="alert">{t(error)}</p>}
            <div className="trial-form-footer">
              <span>{accepted.filter(Boolean).length}<T>{" / 2 tinanggap"}</T></span>
              <button className="button primary" disabled={busy || !accepted.every(Boolean)}>
                {busy ? <><LoaderCircle className="spin" size={17} /><T>{" Inihahanda…"}</T></> : <><T>{"Tanggapin at magsimula "}</T><ArrowRight size={17} /></>}
              </button>
            </div>
          </form>
        </section>
        <aside className="trial-panel trial-included">
          <p className="kicker">GUEST TRIAL</p>
          <h2><T>{"Tatlong paraan para mag-check."}</T></h2>
          <p style={{ fontSize: "14px", color: "var(--soft)", marginBottom: "16px" }}>
            No account required (<Link to="/register" style={{ color: "var(--ph-blue)", textDecoration: "underline", fontWeight: 600 }}><T>{"Gumawa ng Account rito"}</T></Link>)
          </p>
          <ul>
            {trialScanners.map(({ key, label, icon: Icon }) => (
              <li key={key}>
                <Icon size={19} />
                <div>
                  <strong>{label}</strong>
                  <span>{key === "text" ? "3 text scans" : key === "image" ? "2 image scans" : "1 fact check"}</span>
                </div>
              </li>
            ))}
          </ul>
          <div className="trial-note">
            <Info size={17} />
            <p><T>{"Rolling 24 oras ang limits para sa libreng pagsubok."}</T></p>
          </div>
          <p className="trial-fine-print"><T>{"Bawat tinanggap na scan request ay gumagamit ng isang trial. Hindi nire-reset ng pag-clear ng cookies ang backend quota."}</T></p>
          <Link className="trial-text-link" to="/auth"><T>{"May account na? Mag-log in "}</T><ArrowRight size={15} />
          </Link>
        </aside>
      </div>
    </TrialLayout>
  );
}

export function GuestScannerPage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryScanner = searchParams.get("scanner") as Scanner | null;
  const initialScanner: Scanner = queryScanner && ["text", "image", "news"].includes(queryScanner) ? queryScanner : "text";

  // Redirect authenticated users to dashboard; enforce agreement for guests
  useEffect(() => {
    if (sessionStorage.getItem("verifai_user")) {
      navigate("/dashboard", { replace: true });
      return;
    }
    const token = localStorage.getItem("verifai_guest");
    if (!token) {
      navigate("/guest/consent", { replace: true });
    }
  }, [navigate]);

  const [quota, setQuota] = useState<Quota>();
  const [kind, setKind] = useState<Scanner>(initialScanner);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [newsMode, setNewsMode] = useState<"text" | "image">("text");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Record<string, unknown>>();
  const dialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const next = searchParams.get("scanner") as Scanner | null;
    if (next && ["text", "image", "news"].includes(next) && next !== kind) {
      setKind(next);
      setResult(undefined);
      setError("");
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setFile(null);
      setPreviewUrl("");
      if (fileInput.current) fileInput.current.value = "";
    }
  }, [searchParams, kind, previewUrl]);

  const exhausted = quota && Object.values(quota.quotas).every(q => q.remaining === 0);

  useEffect(() => {
    if (exhausted && !dialog.current?.open) {
      dialog.current?.showModal();
    }
  }, [exhausted]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    const refresh = () => getQuota().then(setQuota).catch(e => {
      setQuota(undefined);
      if (axios.isAxiosError(e) && e.response?.status === 401) {
        localStorage.removeItem("verifai_guest");
        navigate("/guest/consent", { replace: true });
      } else {
        setError(guestError(e));
      }
    });
    void refresh();
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(refresh, 15000);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [navigate]);

  const handleSelectedFile = (selected?: File) => {
    setError("");
    if (!selected) return;
    if (selected.size > 10 * 1024 * 1024) {
      setError(`${selected.name} exceeds the 10 MB limit.`);
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(selected);
    setPreviewUrl(URL.createObjectURL(selected));
    setResult(undefined);
  };

  const clearFile = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl("");
    setResult(undefined);
    if (fileInput.current) fileInput.current.value = "";
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const next = e.target.files?.[0];
    if (next) handleSelectedFile(next);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) handleSelectedFile(dropped);
  };

  const pasteClipboard = async () => {
    try {
      const clip = await navigator.clipboard.readText();
      setText(clip.slice(0, 10000));
      setError("");
    } catch {
      setError("Clipboard access blocked. Please use Ctrl+V or paste directly.");
    }
  };

  async function scan() {
    const token = localStorage.getItem("verifai_guest");
    if (!token) {
      navigate("/guest/consent", { replace: true });
      return;
    }
    if (!quota?.quotas[kind].remaining || busy) return;
    setBusy(true);
    setError("");
    setResult(undefined);
    try {
      let data: Record<string, unknown>;
      if (kind === "image") {
        if (!file) {
          setError("Please select an image to analyze.");
          setBusy(false);
          return;
        }
        const form = new FormData();
        form.append("image", file, file.name);
        const res = await api.post("/guest/detect-image", form, {
          headers: { ...guestHeaders(), "Content-Type": undefined },
          timeout: 180000,
        });
        data = res.data;
      } else if (kind === "news") {
        if (newsMode === "image") {
          if (!file) {
            setError("Please upload a news screenshot to verify.");
            setBusy(false);
            return;
          }
          const form = new FormData();
          form.append("image", file, file.name);
          const res = await api.post("/guest/verify-news-image", form, {
            headers: { ...guestHeaders(), "Content-Type": undefined },
            timeout: 180000,
          });
          data = res.data;
        } else {
          if (text.trim().length < 5) {
            setError("Please enter at least 5 characters from the claim.");
            setBusy(false);
            return;
          }
          const res = await api.post("/guest/verify-news", { text: text.trim() }, {
            headers: guestHeaders(),
            timeout: 180000,
          });
          data = res.data;
        }
      } else {
        if (text.trim().length < 20) {
          setError("Please enter or upload at least 20 characters for text analysis.");
          setBusy(false);
          return;
        }
        const res = await api.post("/guest/detect-text", { text: text.trim() }, {
          headers: guestHeaders(),
          timeout: 180000,
        });
        data = res.data;
      }
      setResult(data);
    } catch (e) {
      setError(guestError(e));
    } finally {
      try {
        setQuota(await getQuota());
      } catch {
        setQuota(undefined);
      }
      setBusy(false);
    }
  }

  const isImageMode = kind === "image" || (kind === "news" && newsMode === "image");

  return (
    <TrialLayout
      page="scanner"
      scanner={kind}
      busy={busy}
      onScannerChange={key => {
        setKind(key);
        setSearchParams({ scanner: key });
        setResult(undefined);
        setError("");
        clearFile();
      }}
    >
      <header className="analyzer-page-heading">
        <h1>{labels[kind]}</h1>
        <p>
          {kind === "text"
            ? "Analyze text for patterns and characteristics of AI-generated writing."
            : kind === "image"
            ? "Analyze images for visible signs of AI generation and manipulation."
            : "Verify claims and cross-reference with credible reporting."}
        </p>
      </header>

      <section className="trial-quota" aria-label="Trial quota" aria-live="polite">
        <div className="trial-quota-heading">
          <strong>Your Free Trial</strong>
          <span>Rolling 24 hours · Shared across web and extension</span>
        </div>
        <div className="trial-meters">
          {trialScanners.map(({ key, label, icon: Icon }) => (
            <article key={key} className={quota?.quotas[key].remaining === 0 ? "is-exhausted" : ""}>
              <div>
                <span><Icon size={16} />{label}</span>
                <strong>{quota ? `${quota.quotas[key].remaining} / ${quota.quotas[key].limit}` : "—"}</strong>
              </div>
              <progress
                max={quota?.quotas[key].limit ?? 1}
                value={quota?.quotas[key].remaining ?? 0}
                aria-label={`${label}: scans remaining`}
              />
              {quota?.quotas[key].remaining === 0 ? (
                <small className="trial-lock"><LockKeyhole size={12} /> Free trial exhausted</small>
              ) : (
                <small>{quota ? "scans remaining" : "Fetching quota…"}</small>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="trial-scanner-grid" aria-label="Content analyzer">
        <article className="analysis-card trial-input-card">
          <div className="analysis-card-heading">
            <span className="analysis-number">
              {isImageMode ? <FileImage size={19} /> : <FileText size={19} />}
            </span>
            <div>
              <h2>
                {kind === "image"
                  ? "Upload an image"
                  : kind === "news"
                  ? "Add news to check"
                  : "Add text"}
              </h2>
              <p>
                {kind === "image"
                  ? "Assess visible AI-generation and manipulation signals."
                  : kind === "news"
                  ? "Paste the story or upload a screenshot to inspect."
                  : "Check an article, message, caption, or written passage."}
              </p>
            </div>
          </div>

          {kind === "news" && (
            <div className="news-input-switch" role="tablist" aria-label="News input type" style={{ marginBottom: "16px" }}>
              <button
                className={newsMode === "text" ? "active" : ""}
                type="button"
                role="tab"
                aria-selected={newsMode === "text"}
                onClick={() => { setNewsMode("text"); setError(""); setResult(undefined); clearFile(); }}
              >
                <FileText size={16} /> Paste text
              </button>
              <button
                className={newsMode === "image" ? "active" : ""}
                type="button"
                role="tab"
                aria-selected={newsMode === "image"}
                onClick={() => { setNewsMode("image"); setError(""); setResult(undefined); }}
              >
                <ImageUp size={16} /> Upload image
              </button>
            </div>
          )}

          <form onSubmit={e => { e.preventDefault(); void scan(); }}>
            {kind === "text" && (
              <TextFileUpload
                disabled={busy || !quota?.quotas[kind].remaining}
                onPaste={() => void pasteClipboard()}
                onLoad={(uploadedText) => { setText(uploadedText); setResult(undefined); setError(""); }}
                onError={setError}
              />
            )}
            {isImageMode ? (
              <>
                <input
                  ref={fileInput}
                  className="visually-hidden"
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif,.heic,.heif"
                  onChange={handleFileChange}
                />
                <div
                  className={`media-dropzone ${dragging ? "dragging" : ""} ${file ? "has-files" : ""}`}
                  onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragOver={(e) => e.preventDefault()}
                  onDragLeave={(e) => {
                    if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
                  }}
                  onDrop={handleDrop}
                >
                  {!file ? (
                    <>
                      <span className="dropzone-icon"><Upload size={22} /></span>
                      <strong>Drop your image here</strong>
                      <p>or choose an image from your device</p>
                      <button
                        className="button secondary"
                        type="button"
                        onClick={() => fileInput.current?.click()}
                        disabled={busy || !quota?.quotas[kind].remaining}
                      >
                        Browse images
                      </button>
                      <small>JPG, PNG, WEBP, GIF, HEIC or HEIF · maximum 10 MB</small>
                    </>
                  ) : (
                    <div className="dropzone-preview-content">
                      <div className="dropzone-preview-heading">
                        <strong>1 file ready</strong>
                        <button type="button" onClick={clearFile}>Clear</button>
                      </div>
                      <div className="dropzone-preview-grid single">
                        <figure>
                          <div className="dropzone-media">
                            {previewUrl ? (
                              <img src={previewUrl} alt={`Preview of ${file.name}`} />
                            ) : (
                              <span><FileImage size={18} /></span>
                            )}
                            <button
                              type="button"
                              aria-label={`Remove ${file.name}`}
                              onClick={clearFile}
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                          <figcaption>
                            <strong>{file.name}</strong>
                            <small>{formatBytes(file.size)}</small>
                          </figcaption>
                        </figure>
                      </div>
                      <small>Drop another file here to replace this one.</small>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="text-input-shell">
                <div className="text-input-toolbar">
                  <span><FileText size={15} /> Text to analyze</span>
                  <div>
                    {text && <button type="button" onClick={() => setText("")}><X size={14} /> Clear</button>}
                  </div>
                </div>
                <textarea
                  id="trial-text"
                  required
                  minLength={kind === "text" ? 20 : 5}
                  maxLength={10000}
                  value={text}
                  disabled={busy || !quota?.quotas[kind].remaining}
                  onChange={e => setText(e.target.value)}
                  placeholder={kind === "news" ? "Paste or type the news story here…" : "Paste text here or upload a .txt file above…"}
                  aria-label="Text to analyze"
                />
                <div className="text-input-meta" style={{ display: "flex", justifyContent: "space-between", padding: "8px 12px", fontSize: "12px", color: "var(--soft)" }}>
                  <span>English, Filipino, and Taglish supported</span>
                  <span>{text.length.toLocaleString()} / 10,000 (Min {kind === "text" ? 20 : 5})</span>
                </div>
              </div>
            )}

            <button
              className="button primary analysis-action"
              style={{ marginTop: "16px" }}
              disabled={
                busy ||
                !quota?.quotas[kind].remaining ||
                (isImageMode && !file) ||
                (!isImageMode && text.trim().length < (kind === "text" ? 20 : 5))
              }
            >
              {busy ? (
                <><LoaderCircle className="spin" size={17} /> Analyzing…</>
              ) : quota?.quotas[kind].remaining === 0 ? (
                <><LockKeyhole size={16} /> Free trial exhausted</>
              ) : (
                <>
                  {kind === "image" ? "Analyze image" : kind === "news" ? "Check this news" : "Analyze text"} <ArrowRight size={17} />
                </>
              )}
            </button>
          </form>

          {error && <p className="trial-error" role="alert" style={{ marginTop: "16px" }}>{t(error)}</p>}
          <p className="trial-fine-print">Analysis is an informational estimate. Review context carefully before sharing.</p>
        </article>

        <aside className="text-result-card trial-result-card" aria-live="polite" aria-busy={busy}>
          <div className="text-result-heading">
            <div>
              <p>Analysis result</p>
              <h2>{kind === "news" ? "Fact-check report" : kind === "image" ? "Media assessment" : "Writing assessment"}</h2>
            </div>
            {result && !busy && <span>Complete</span>}
          </div>

          {busy ? (
            <div className="text-result-loading" style={{ padding: "24px" }}>
              <LoaderCircle className="spin" size={24} />
              <div>
                <strong>Analyzing content…</strong>
                <span>
                  {kind === "text"
                    ? "Evaluating text patterns against AI writing classifiers…"
                    : kind === "image"
                    ? "Inspecting visual signals, lighting, textures, and anomalies…"
                    : "Searching trusted news outlets and corroborating claims…"}
                </span>
              </div>
            </div>
          ) : result ? (
            <div className="trial-result-content">
              {kind === "text" && <TextScanResultView data={result as unknown as TextScanData} />}
              {kind === "image" && <MediaScanResultView data={result as unknown as MediaScanData} />}
              {kind === "news" && <NewsScanResultView data={result as unknown as NewsVerificationData} />}
            </div>
          ) : (
            <div className="trial-empty">
              <FileText size={28} />
              <h3>Your results will appear here</h3>
              <p>Submit content above to inspect authenticity signals and detailed evidence.</p>
            </div>
          )}
        </aside>
      </section>

      <dialog ref={dialog} className="trial-modal" aria-labelledby="trial-conversion-title">
        <span className="analysis-number"><ShieldCheck size={20} /></span>
        <h2 id="trial-conversion-title">Enjoying Verif.AI?</h2>
        <p>You have exhausted your free trial scans for this rolling 24-hour period. Create a Free Account for unlimited scans and access to all features.</p>
        <p className="trial-fine-print">Service rate limits still apply to keep Verif.AI reliably available.</p>
        <div className="trial-modal-actions">
          <Link className="button primary" to="/register">Create Free Account <ArrowRight size={16} /></Link>
          <button className="button secondary" onClick={() => dialog.current?.close()}>View Results</button>
        </div>
      </dialog>
    </TrialLayout>
  );
}
