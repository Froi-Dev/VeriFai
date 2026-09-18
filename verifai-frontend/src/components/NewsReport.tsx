import { useState } from "react";
import { ExternalLink, Info, Newspaper } from "lucide-react";

export type ReportSource = {
  title: string;
  publisher: string;
  url: string;
  image_url?: string;
  explanation?: string;
  relationship?: string;
};

export type ReportClaim = {
  claim: string;
  verdict: string;
  explanation: string;
  source_urls?: string[];
};

type NewsReportProps = {
  claims?: ReportClaim[];
  verdict?: string;
  tone: string;
  confidence?: number;
  heading: string;
  explanation: string;
  warnings?: string[];
  closestStory?: ReportSource | null;
  sources: ReportSource[];
};

function SourceImage({ source }: { source: ReportSource }) {
  const [failedUrl, setFailedUrl] = useState<string>();
  const imageUrl = source.image_url;
  const hasImage = imageUrl && /^https?:\/\//i.test(imageUrl) && failedUrl !== imageUrl;

  return (
    <span className={`report-source-image${hasImage ? "" : " is-unavailable"}`}>
      {hasImage ? (
        <img
          src={imageUrl}
          alt={`Image from ${source.publisher}: ${source.title}`}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(imageUrl)}
        />
      ) : (
        <>
          <Newspaper size={22} aria-hidden="true" />
          <small>No image available</small>
        </>
      )}
    </span>
  );
}

function relationshipLabel(relationship?: string) {
  if (relationship === "SUPPORTS") return "Supports this news";
  if (relationship === "CONTRADICTS") return "Reports different facts";
  if (relationship === "DEBUNKS") return "Debunks this claim";
  return "Related report";
}

export function NewsReport({
  verdict,
  tone,
  confidence,
  heading,
  explanation,
  warnings = [],
  closestStory,
  sources,
}: NewsReportProps) {
  const contextWarnings = warnings.filter(
    (warning) =>
      !warning.startsWith("This input looks like a short headline.") &&
      !warning.includes("Verified using search snippets") &&
      !warning.includes("full article contents were not retrieved")
  );

  return (
    <div className="news-result-content unified-news-report">
      <section className="news-verdict" aria-labelledby="news-verdict-heading">
        <div className="news-verdict-meta">
          {verdict && (
            <span className="news-verdict-label" data-news-result={tone}>
              <i aria-hidden="true" />
              {verdict}
            </span>
          )}
          <strong className="news-verdict-confidence">
            {confidence !== undefined ? `Confidence: ${confidence}%` : "Please try again later"}
          </strong>
        </div>
        <h3 id="news-verdict-heading">{heading}</h3>
        <p className="news-verdict-summary">{explanation}</p>
        {contextWarnings.map((warning, index) => (
          <div className="report-context-note" role="note" key={`${index}-${warning}`}>
            <Info size={16} />
            <span>{warning}</span>
          </div>
        ))}
      </section>

      {closestStory && (
        <article className="closest-story">
          <SourceImage source={closestStory} />
          <div>
            <small>CLOSEST MATCHING REPORT</small>
            <h3>{closestStory.title}</h3>
            <p>{closestStory.explanation}</p>
            <a href={closestStory.url} target="_blank" rel="noreferrer">
              Read on {closestStory.publisher || "the original source"} <ExternalLink size={13} />
            </a>
          </div>
        </article>
      )}

      {sources.length > 0 && (
        <div className="source-list">
          <div className="source-list-heading">
            <h3>Sources checked</h3>
            <span>
              {sources.length} {sources.length === 1 ? "report" : "reports"}
            </span>
          </div>
          {sources.map((source) => (
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              key={`${source.relationship}-${source.url}`}
            >
              <SourceImage source={source} />
              <div>
                <strong>{source.publisher}</strong>
                <span className="report-relationship">{relationshipLabel(source.relationship)}</span>
                <p>{source.title}</p>
              </div>
              <ExternalLink size={16} />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
