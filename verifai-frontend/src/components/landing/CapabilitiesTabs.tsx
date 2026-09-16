import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Cpu,
  Globe,
  Image as ImageIcon,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";

const assetPath = (path: string) =>
  `${import.meta.env.BASE_URL}${path.replace(/^\//, "")}`;

type WorkflowStepItem = {
  step: string;
  title: string;
  desc: string;
  badge: string;
};

type Capability = {
  id: string;
  tabLabel: string;
  icon: typeof Cpu;
  title: string;
  subtitle: string;
  description: string;
  steps: WorkflowStepItem[];
  specs: { label: string; value: string }[];
  image: string;
  imageAlt: string;
};

const CAPABILITIES: Capability[] = [
  {
    id: "text-intelligence",
    tabLabel: "AI Text Detector",
    icon: Cpu,
    title: "AI Writing & Taglish Detector",
    subtitle: "English · Filipino · Taglish Code-Switching",
    description:
      "Detect synthetic phrasing, automated summaries, and AI-generated passages in Filipino, Taglish, and English. Verif.Ai inspects sentence cadence, code-switching nuance, and repetitive formulas to provide clear likelihood scores and highlighted writing clues.",
    steps: [
      {
        step: "01",
        title: "Submit Passage",
        desc: "Paste any article, student essay, caption, or casual Taglish social media post.",
        badge: "Input",
      },
      {
        step: "02",
        title: "Scan Cadence & Formulas",
        desc: "Neural models evaluate repetitive phrasing, uniform robotic rhythm, and chatbot transition habits.",
        badge: "Analysis",
      },
      {
        step: "03",
        title: "Review Score & Clues",
        desc: "Receive calibrated AI vs. Human likelihood scores with explicit pattern tags to guide review.",
        badge: "Assessment",
      },
    ],
    specs: [
      { label: "Languages", value: "Taglish, Filipino & English" },
      { label: "Latency", value: "Under 1 Second" },
      { label: "Telemetry", value: "AI vs. Human Breakdown" },
      { label: "Clues", value: "Detected Pattern Chips" },
    ],
    image: assetPath("/images/text-analyzer-preview.png"),
    imageAlt: "Verif.Ai Text Analyzer workspace preview showing AI writing assessment and detected pattern highlights",
  },
  {
    id: "news-verification",
    tabLabel: "News & Claim Verifier",
    icon: Globe,
    title: "Real-Time News & Fact Checking",
    subtitle: "Viral Claims · News Outlets · Fact Checks",
    description:
      "Paste any breaking news story, suspicious announcement, or viral headline. Verif.Ai extracts factual claims and compares them directly against verified Philippine news publishers and primary sources with side-by-side corroboration.",
    steps: [
      {
        step: "01",
        title: "Submit News or Screenshot",
        desc: "Paste breaking news text or upload a headline screenshot with automated OCR extraction.",
        badge: "Claim Input",
      },
      {
        step: "02",
        title: "Cross-Corroborate Sources",
        desc: "Live search queries verified Philippine news agencies, accredited fact-checkers, and primary records.",
        badge: "Search & Match",
      },
      {
        step: "03",
        title: "Inspect Evidence & Certainty",
        desc: "See a clear verdict (e.g. Real News, 95% sure) with direct source links and tier ratings.",
        badge: "Corroboration",
      },
    ],
    specs: [
      { label: "Sources", value: "Primary & Major Media" },
      { label: "Coverage", value: "National & Regional News" },
      { label: "Evidence", value: "Side-by-Side Reports" },
      { label: "Search Mode", value: "Live Real-Time Search" },
    ],
    image: assetPath("/images/news-analyzer-preview.png"),
    imageAlt: "Verif.Ai Fake News Analyzer workspace showing claim corroboration with Philippine News Agency and ABS-CBN reports",
  },
  {
    id: "media-analyzer",
    tabLabel: "Image Verifier",
    icon: ImageIcon,
    title: "Image & Screenshot Verifier",
    subtitle: "Social Posts · Memes · Infographics · Photos",
    description:
      "Check suspicious photos, viral screenshots, and social media graphics before you share them. Verif.Ai reads text inside screenshots using OCR and inspects images for visual signs of AI generation or tampering.",
    steps: [
      {
        step: "01",
        title: "Upload Photo or Graphic",
        desc: "Drop any PNG, JPG, WebP screenshot or announcement card for immediate inspection.",
        badge: "Drop & Scan",
      },
      {
        step: "02",
        title: "Inspect Visual Artifacts",
        desc: "Detects painterly AI textures, synthetic lighting anomalies, facial warping, and strange typography.",
        badge: "Visual Clues",
      },
      {
        step: "03",
        title: "Plain-Language Summary",
        desc: "Delivers an objective assessment (e.g. 98% AI Likelihood) with key observations to guide your judgment.",
        badge: "Verdict",
      },
    ],
    specs: [
      { label: "Accepted Media", value: "PNG, JPG, WebP, Screenshots" },
      { label: "Text Extraction", value: "Built-in Image OCR" },
      { label: "Inspection", value: "Visual & Content Clues" },
      { label: "Result", value: "Plain-Language Summary" },
    ],
    image: assetPath("/images/media-analyzer-preview.png"),
    imageAlt: "Verif.Ai Media Assessment and Image Verifier real workspace preview",
  },
];

export function CapabilitiesTabs() {
  const reduceMotion = useReducedMotion();

  return (
    <div className="capabilities-scroll-list">
      {CAPABILITIES.map((cap, index) => {
        const Icon = cap.icon;

        return (
          <motion.article
            key={cap.id}
            id={cap.id}
            className="capability-featured-block"
            initial={reduceMotion ? false : { opacity: 0, y: 36 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.15 }}
            transition={{ duration: 0.6, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
          >
            {/* Header / Intro Strip */}
            <div className="cap-block-header">
              <div className="cap-meta-row">
                <span className="cap-module-pill">
                  <Icon size={14} className="cap-module-icon" />
                  <span>Module 0{index + 1} · {cap.tabLabel}</span>
                </span>
                <span className="cap-badge-pill">{cap.subtitle}</span>
              </div>
              <h2>{cap.title}</h2>
              <p className="cap-lead-desc">{cap.description}</p>
            </div>

            {/* Enlarged Prominent Visual Workspace Display */}
            <div className="capability-large-visual-wrap">
              <div className="cap-preview-window">
                <div className="cap-preview-toolbar">
                  <div className="window-dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </div>
                  <span className="cap-toolbar-tag">
                    <Sparkles size={12} className="cap-toolbar-icon" />
                    {cap.tabLabel} · Live Workspace Preview
                  </span>
                  <span className="cap-toolbar-model">
                    <ShieldCheck size={13} /> Verified Workflow
                  </span>
                </div>

                <div className="cap-image-shell">
                  <img
                    src={cap.image}
                    alt={cap.imageAlt}
                    className="cap-display-img"
                    loading="lazy"
                  />
                </div>
              </div>
            </div>

            {/* Integrated "How It Works" 3-Step Pipeline For This Module */}
            <div className="cap-module-workflow">
              <div className="cap-workflow-intro">
                <span className="cap-workflow-tag">How it works</span>
                <h3>Verification in 3 simple steps</h3>
              </div>

              <div className="cap-workflow-steps-grid">
                {cap.steps.map((item) => (
                  <div key={item.step} className="cap-step-card">
                    <div className="cap-step-card-head">
                      <span className="cap-step-number">{item.step}</span>
                      <span className="cap-step-badge">{item.badge}</span>
                    </div>
                    <strong className="cap-step-title">{item.title}</strong>
                    <p className="cap-step-desc">{item.desc}</p>
                  </div>
                ))}
              </div>

              {/* Module Specs Footer & Action Link */}
              <div className="cap-block-footer">
                <div className="cap-specs-grid">
                  {cap.specs.map((spec) => (
                    <div key={spec.label} className="spec-item">
                      <span className="spec-label">{spec.label}</span>
                      <strong className="spec-val">{spec.value}</strong>
                    </div>
                  ))}
                </div>

                <div className="cap-action-row">
                  <Link to="/auth" className="button primary large">
                    Launch {cap.tabLabel} <ArrowRight size={16} />
                  </Link>
                </div>
              </div>
            </div>
          </motion.article>
        );
      })}
    </div>
  );
}

