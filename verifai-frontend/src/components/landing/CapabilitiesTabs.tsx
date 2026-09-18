import { FileText, Newspaper, Image, Maximize2, Check } from "lucide-react";
import { Link } from "react-router-dom";

const capabilities = [
  {
    id: "text-intelligence",
    icon: FileText,
    name: "Text Analyzer",
    title: "A closer look at the writing.",
    description:
      "Check English, Filipino, and Taglish passages for patterns associated with AI-generated writing. Review the assessment alongside the original text.",
    points: [
      "AI and human writing pattern scores",
      "Writing clues to support your review",
      "A separate assessment from news accuracy",
    ],
    image: "dashboard-text-analyzer.png",
    alt: "The actual VeriFai Text Analyzer interface",
  },
  {
    id: "news-verification",
    icon: Newspaper,
    name: "News Checker",
    title: "Follow the claim. Find the evidence.",
    description:
      "Check a headline, a story, or the text in a screenshot against Philippine news coverage. Read the supporting and contradicting sources before drawing a conclusion.",
    points: [
      "Text claims and news screenshots",
      "Source links you can inspect yourself",
      "Context and uncertainty alongside the verdict",
    ],
    image: "news-analyzer-preview.png",
    alt: "The actual VeriFai News Checker interface",
  },
  {
    id: "media-analyzer",
    icon: Image,
    name: "Media Analyzer",
    title: "Look beyond the first impression.",
    description:
      "Upload a photo or graphic to inspect visible signs of AI generation and manipulation. Understand the observations and the limits of the assessment.",
    points: [
      "Image uploads and drag-and-drop",
      "A plain-language visual assessment",
      "Visible clues, confidence, and limitations",
    ],
    image: "dashboard-media-analyzer.png",
    alt: "The actual VeriFai Media Analyzer interface",
  },
];

export function CapabilitiesTabs() {
  return (
    <div className="verification-features">
      {capabilities.map(
        ({ id, icon: Icon, name, title, description, points, image, alt }) => {
          const source = `${import.meta.env.BASE_URL}images/${image}`;
          return (
            <article className="verification-feature" id={id} key={id}>
              <div className="verification-feature-copy">
                <span className="feature-tool-name">
                  <Icon size={20} />
                  {name}
                </span>
                <h3>{title}</h3>
                <p>{description}</p>
                <ul>
                  {points.map((point) => (
                    <li key={point}>
                      <Check size={16} />
                      {point}
                    </li>
                  ))}
                </ul>
                <Link className="button secondary" to="/auth">
                  Open {name}
                </Link>
              </div>
              <figure className="feature-capture">
                <a
                  href={source}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`View full-size ${name} screenshot`}
                >
                  <img
                    src={source}
                    alt={alt}
                    width={1440}
                    height={960}
                    loading="lazy"
                  />
                </a>
                <figcaption>
                  <span>{name} workspace</span>
                  <a href={source} target="_blank" rel="noreferrer">
                    View full size <Maximize2 size={13} />
                  </a>
                </figcaption>
              </figure>
            </article>
          );
        },
      )}
    </div>
  );
}
