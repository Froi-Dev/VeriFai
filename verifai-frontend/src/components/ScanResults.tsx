import { Check, Info } from "lucide-react";
import { NewsReport, type ReportClaim, type ReportSource } from "@/components/NewsReport";

export type TextScanData = {
  classification: "Likely AI-generated" | "Likely human-written" | "Review recommended" | string;
  confidence: number;
  ai_probability?: number;
  human_probability?: number;
  aiConfidence?: number;
  humanConfidence?: number;
  signals?: string[];
  explanation?: string;
};

export type MediaScanData = {
  classification: string;
  confidence: number;
  ai_probability?: number;
  authentic_probability?: number;
  aiConfidence?: number;
  humanConfidence?: number;
  summary: string;
  signals?: string[];
  limitations?: string;
};

export type NewsEvidenceItem = {
  title: string;
  publisher: string;
  url: string;
  domain?: string;
  published_date?: string | null;
  image_url?: string;
  relationship: string;
  similarity?: number;
  evidence_score?: number;
  source_tier?: number;
  source_type?: string;
  reliability?: number;
  explanation?: string;
  evidence_text?: string;
};

export type NewsVerificationData = {
  status?: string;
  verdict: string;
  confidence: number;
  explanation: string;
  claim_results?: ReportClaim[];
  context_warnings?: string[];
  evidence?: {
    supporting?: NewsEvidenceItem[];
    contradicting?: NewsEvidenceItem[];
    related?: NewsEvidenceItem[];
    debunks?: NewsEvidenceItem[];
  };
  closest_real_story?: {
    found: boolean;
    title: string;
    publisher: string;
    url: string;
    date?: string;
    similarity?: number;
    explanation?: string;
    image_url?: string;
  };
};

function formatSignalTag(sig: string): string {
  const lower = sig.toLowerCase();
  if (lower.includes("summary") || lower.includes("transition")) return "Chatbot summary phrasing";
  if (lower.includes("progress") || lower.includes("teleological")) return "Step-by-step robotic phrasing";
  if (lower.includes("cosmological") || lower.includes("science") || lower.includes("explainer")) return "Textbook-style formula";
  if (lower.includes("temporal") || lower.includes("timescale")) return "Formulaic timeline phrase";
  if (lower.includes("evidentiary") || lower.includes("didactic")) return "Repetitive academic structure";
  if (lower.includes("anchor") || lower.includes("trope")) return "Predictable AI cliché";
  if (lower.includes("conversational")) return "Chatbot conversational style";
  if (lower.includes("listicle")) return "Bulleted list structure";
  if (lower.includes("corporate")) return "Buzzword phrasing";
  return sig;
}

export function TextScanResultView({ data }: { data: TextScanData }) {
  // Normalize confidence values: if <= 1, convert to percentage
  const aiConf = data.aiConfidence ?? (data.ai_probability !== undefined ? Math.round(data.ai_probability > 1 ? data.ai_probability : data.ai_probability * 100) : (data.confidence > 1 ? Math.round(data.confidence) : Math.round(data.confidence * 100)));
  const humanConf = data.humanConfidence ?? (data.human_probability !== undefined ? Math.round(data.human_probability > 1 ? data.human_probability : data.human_probability * 100) : 100 - aiConf);
  
  const classification = data.classification;
  const tone = classification === "Likely AI-generated" ? "ai" : classification === "Likely human-written" ? "human" : "review";

  const description = data.explanation || (
    classification === "Likely AI-generated"
      ? "This text looks like it was written or assisted by AI."
      : classification === "Likely human-written"
        ? "This text reads naturally like regular human writing."
        : "This text shows mixed characteristics, so reviewing it yourself is recommended."
  );

  const rawSignals = data.signals ?? [];
  const processedTags = Array.from(new Set(rawSignals.map(formatSignalTag))).slice(0, 3);

  return (
    <div className="text-result-content">
      <div className="plain-verdict writing-verdict" data-writing-result={tone}>
        <span>Overall assessment</span>
        <h3>{classification}</h3>
        <p>{description}</p>
      </div>

      <div className="likelihood-bars">
        <div>
          <div className="writing-score-ai">
            <span>AI writing pattern score</span>
            <strong>{aiConf}%</strong>
          </div>
          <span className="likelihood-track">
            <i className="ai-bar" style={{ width: `${aiConf}%` }} />
          </span>
        </div>
        <div>
          <div className="writing-score-human">
            <span>Human writing pattern score</span>
            <strong>{humanConf}%</strong>
          </div>
          <span className="likelihood-track">
            <i className="human-bar" style={{ width: `${humanConf}%` }} />
          </span>
        </div>
      </div>

      <div className="plain-evidence">
        <h3>Key Highlights</h3>
        <ul>
          {processedTags.length > 0 ? (
            <li>
              <Check size={15} />
              <span>
                <strong>AI Patterns Detected:</strong>
                <span style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "6px" }}>
                  {processedTags.map((tag) => (
                    <span
                      key={tag}
                      style={{
                        padding: "3px 8px",
                        borderRadius: "4px",
                        background: "#fef3c7",
                        color: "#92400e",
                        fontSize: "11px",
                        fontWeight: 600,
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </span>
              </span>
            </li>
          ) : (
            <li>
              <Check size={15} />
              <span>
                <strong>Natural Writing:</strong> No robotic phrasing or repetitive chatbot patterns detected.
              </span>
            </li>
          )}
        </ul>
      </div>

      <p className="result-caution">
        <Info size={14} /> AI detectors give likelihood estimates, not definitive proof.
      </p>
    </div>
  );
}

export function MediaScanResultView({ data }: { data: MediaScanData }) {
  const aiProb = data.ai_probability ?? data.aiConfidence ?? (100 - (data.authentic_probability ?? 50));
  const authProb = data.authentic_probability ?? data.humanConfidence ?? (100 - aiProb);
  const conf = data.confidence > 1 ? Math.round(data.confidence) : Math.round(data.confidence * 100);

  return (
    <div className="text-result-content">
      <div className="plain-verdict">
        <span>Overall assessment · {conf}% CONFIDENCE</span>
        <h3>{data.classification}</h3>
        <p>{data.summary}</p>
      </div>

      <div className="likelihood-bars">
        <div>
          <div>
            <span>AI-generation likelihood</span>
            <strong>{aiProb}%</strong>
          </div>
          <span className="likelihood-track">
            <i className="ai-bar" style={{ width: `${aiProb}%` }} />
          </span>
        </div>
        <div>
          <div>
            <span>Authentic/camera-captured likelihood</span>
            <strong>{authProb}%</strong>
          </div>
          <span className="likelihood-track">
            <i className="human-bar" style={{ width: `${authProb}%` }} />
          </span>
        </div>
      </div>

      {data.signals && data.signals.length > 0 && (
        <div className="plain-evidence">
          <h3>Visible signals considered</h3>
          <ul>
            {data.signals.map((signal) => (
              <li key={signal}>
                <Check size={15} />
                <span>{signal}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="result-caution">
        <Info size={14} /> {data.limitations || "Visual analysis is an estimate, not forensic proof. Check provenance and metadata too."}
      </p>
    </div>
  );
}

function formatNewsVerdict(verdict: string): string {
  const labels: Record<string, string> = {
    VERIFIED: "Real news",
    LIKELY_TRUE: "Likely real",
    MISLEADING: "Misleading",
    UNVERIFIED: "Not enough information",
    LIKELY_FALSE: "Likely fake",
    FALSE: "Fake news",
    SATIRE: "Satire / Parody",
    OUTDATED: "Outdated",
  };
  return labels[verdict] || verdict;
}

function newsVerdictTone(verdict: string): string {
  if (verdict === "VERIFIED" || verdict === "LIKELY_TRUE") return "real";
  if (verdict === "UNVERIFIED") return "uncertain";
  if (verdict === "MISLEADING" || verdict === "OUTDATED" || verdict === "SATIRE") return "warning";
  return "fake";
}

function newsVerdictHeading(data: NewsVerificationData): string {
  if (data.status === "SEARCH_UNAVAILABLE") {
    return "We could not check this news right now.";
  }
  const verdict = data.verdict;
  if (verdict === "VERIFIED" || verdict === "LIKELY_TRUE") {
    return "This news matches reliable sources.";
  }
  if (verdict === "MISLEADING") return "This news has misleading details.";
  if (verdict === "UNVERIFIED") return "There is not enough evidence yet.";
  if (verdict === "LIKELY_FALSE") return "This news is likely false.";
  if (verdict === "SATIRE") return "This appears to be satire or parody.";
  if (verdict === "OUTDATED") return "This is old news presented as new.";
  return "Reliable sources show this news is false.";
}

export function NewsScanResultView({ data }: { data: NewsVerificationData }) {
  const evidenceList: ReportSource[] = [];
  if (data.evidence) {
    const rawItems = [
      ...(data.evidence.debunks || []),
      ...(data.evidence.contradicting || []),
      ...(data.evidence.supporting || []),
      ...(data.evidence.related || []),
    ];
    for (const item of rawItems) {
      if (!evidenceList.some((e) => e.url === item.url)) {
        evidenceList.push({
          title: item.title,
          publisher: item.publisher,
          url: item.url,
          relationship: item.relationship,
          image_url: item.image_url,
        });
      }
    }
  }

  const closestStory = data.closest_real_story?.found
    ? {
        title: data.closest_real_story.title,
        publisher: data.closest_real_story.publisher,
        url: data.closest_real_story.url,
        explanation: data.closest_real_story.explanation || "",
        image_url: data.closest_real_story.image_url,
      }
    : evidenceList.length > 0
    ? {
        title: evidenceList[0].title,
        publisher: evidenceList[0].publisher,
        url: evidenceList[0].url,
        explanation: evidenceList[0].title,
        image_url: evidenceList[0].image_url,
      }
    : null;

  const displayedSources = closestStory
    ? evidenceList.filter((s) => s.url !== closestStory.url).slice(0, 6)
    : evidenceList.slice(0, 6);

  const showVerdict = data.status !== "SEARCH_UNAVAILABLE";

  return (
    <NewsReport
      verdict={showVerdict ? formatNewsVerdict(data.verdict) : undefined}
      tone={newsVerdictTone(data.verdict)}
      confidence={showVerdict ? data.confidence : undefined}
      heading={newsVerdictHeading(data)}
      explanation={data.explanation}
      claims={data.claim_results}
      warnings={data.context_warnings || []}
      closestStory={closestStory}
      sources={displayedSources}
    />
  );
}
