import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  CheckCircle,
  Cpu,
  Layers,
  Search,
  ShieldAlert,
  Sliders,
} from "lucide-react";
import { Link } from "react-router-dom";

type WorkflowStep = {
  id: string;
  stepNum: string;
  title: string;
  shortDesc: string;
  badge: string;
  details: string;
};

const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "step-1",
    stepNum: "01",
    title: "Submit Content",
    shortDesc: "Paste text, drop a file, or upload a social media screenshot.",
    badge: "Step 1",
    details:
      "Enter any passage or upload a screenshot. Verif.Ai recognizes Filipino, English, and natural Taglish conversational code-switching instantly.",
  },
  {
    id: "step-2",
    stepNum: "02",
    title: "Scan Writing Patterns",
    shortDesc: "Checks for natural human rhythm versus robotic AI formulas.",
    badge: "Step 2",
    details:
      "Verif.Ai looks for natural human variety versus telltale AI patterns—such as overly uniform sentences, repetitive transitions, or formal textbook wording.",
  },
  {
    id: "step-3",
    stepNum: "03",
    title: "Review Clues & Confidence",
    shortDesc: "Get a transparent score and highlighted clues to guide your judgment.",
    badge: "Step 3",
    details:
      "You get a straightforward result: Likely Human, Review Recommended, or Likely AI. Clear explanations show you why, so you're always in control.",
  },
];

export function WorkflowInteractive() {
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const reduceMotion = useReducedMotion();

  const currentStep = WORKFLOW_STEPS[activeStepIndex];

  return (
    <div className="workflow-grid">
      {/* Left Column: Interactive Step Selector */}
      <div className="steps-interactive" role="tablist" aria-label="Workflow pipeline steps">
        {WORKFLOW_STEPS.map((step, idx) => {
          const isActive = idx === activeStepIndex;
          return (
            <button
              key={step.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`step-interactive-item ${isActive ? "active" : ""}`}
              onClick={() => setActiveStepIndex(idx)}
            >
              <div className="step-num-badge">
                <span>{step.stepNum}</span>
              </div>
              <div className="step-content-text">
                <div className="step-header-row">
                  <h3>{step.title}</h3>
                  <span className="step-tag-pill">{step.badge}</span>
                </div>
                <p>{step.shortDesc}</p>
              </div>
            </button>
          );
        })}

        <div className="workflow-footer-cta">
          <Link to="/auth" className="inline-link">
            Explore live verification tools <ArrowRight size={14} />
          </Link>
        </div>
      </div>

      {/* Right Column: Dynamic Pipeline Visualizer */}
      <div className="workflow-visual-card">
        <div className="workflow-card-toolbar">
          <div className="window-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
          <span className="workflow-toolbar-title">
            Pipeline Inspection · Stage {currentStep.stepNum}
          </span>
          <span className="workflow-status-live">
            <i className="pulse-dot" /> Active Pipeline
          </span>
        </div>

        <motion.div
          key={currentStep.id}
          className="workflow-visual-body"
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
        >
          {activeStepIndex === 0 && (
            <div className="stage-panel stage-tokenization">
              <div className="stage-head">
                <Layers size={18} className="stage-icon" />
                <div>
                  <strong>Text & Language Reader</strong>
                  <small>Recognizes Taglish, Filipino, and English naturally</small>
                </div>
              </div>

              <p className="stage-desc">{currentStep.details}</p>

              <div className="token-preview-stream">
                <span className="stream-label">Sample Word Scan (Taglish):</span>
                <div className="token-chips">
                  <span className="token-chip prefix">[Start]</span>
                  <span className="token-chip">Napak</span>
                  <span className="token-chip">ahalaga</span>
                  <span className="token-chip">na</span>
                  <span className="token-chip">tandaan</span>
                  <span className="token-chip highlight-token">sa</span>
                  <span className="token-chip highlight-token">gc</span>
                  <span className="token-chip">natin</span>
                  <span className="token-chip">bukas</span>
                  <span className="token-chip suffix">[End]</span>
                </div>
              </div>

              <div className="stage-metrics-row">
                <div className="metric-box">
                  <span className="metric-title">Input Types</span>
                  <strong className="metric-val">Text & Media</strong>
                  <span className="metric-sub">Articles & screenshots</span>
                </div>
                <div className="metric-box">
                  <span className="metric-title">Languages</span>
                  <strong className="metric-val">Taglish / Filipino</strong>
                  <span className="metric-sub">Plus standard English</span>
                </div>
                <div className="metric-box">
                  <span className="metric-title">Speed</span>
                  <strong className="metric-val">&lt; 1s</strong>
                  <span className="metric-sub">Instant response</span>
                </div>
              </div>
            </div>
          )}

          {activeStepIndex === 1 && (
            <div className="stage-panel stage-attention">
              <div className="stage-head">
                <Cpu size={18} className="stage-icon" />
                <div>
                  <strong>Writing Pattern Analysis</strong>
                  <small>Identifies natural variation vs. robotic habits</small>
                </div>
              </div>

              <p className="stage-desc">{currentStep.details}</p>

              <div className="attention-metrics-list">
                <div className="attention-metric-item">
                  <div className="metric-header">
                    <span>Repetitive Phrasing</span>
                    <strong>Formulaic (91%)</strong>
                  </div>
                  <div className="metric-bar-track">
                    <div className="metric-bar-fill" style={{ width: "91%" }} />
                  </div>
                </div>

                <div className="attention-metric-item">
                  <div className="metric-header">
                    <span>Robotic Sentence Cadence</span>
                    <strong>Elevated (88%)</strong>
                  </div>
                  <div className="metric-bar-track">
                    <div className="metric-bar-fill" style={{ width: "88%" }} />
                  </div>
                </div>

                <div className="attention-metric-item">
                  <div className="metric-header">
                    <span>Overused AI Transitions</span>
                    <strong>Frequent ('Bukod dito')</strong>
                  </div>
                  <div className="metric-bar-track">
                    <div className="metric-bar-fill" style={{ width: "76%" }} />
                  </div>
                </div>
              </div>

              <div className="stage-info-pill">
                <Activity size={14} />
                <span>Scanning for telltale writing habits common in AI chatbots</span>
              </div>
            </div>
          )}

          {activeStepIndex === 2 && (
            <div className="stage-panel stage-calibration">
              <div className="stage-head">
                <Sliders size={18} className="stage-icon" />
                <div>
                  <strong>Confidence Breakdown</strong>
                  <small>Empowers human judgment with clear guidance</small>
                </div>
              </div>

              <p className="stage-desc">{currentStep.details}</p>

              {/* Threshold Range Diagram */}
              <div className="threshold-spectrum">
                <div className="spectrum-zones">
                  <div className="zone human-zone">
                    <CheckCircle size={13} />
                    <span>Likely Human (≤26%)</span>
                  </div>
                  <div className="zone review-zone">
                    <Search size={13} />
                    <span>Needs Review (26% - 50%)</span>
                  </div>
                  <div className="zone ai-zone">
                    <ShieldAlert size={13} />
                    <span>Likely AI (≥50%)</span>
                  </div>
                </div>
                <div className="spectrum-ruler">
                  <span className="tick">0%</span>
                  <span className="tick marker-1">26%</span>
                  <span className="tick marker-2">50%</span>
                  <span className="tick">100%</span>
                </div>
              </div>

              <div className="stage-summary-badge">
                <span className="badge-tag">Why this matters:</span>
                <span className="badge-desc">
                  When writing or claims fall in the review zone, Verif.Ai recommends double-checking verified sources rather than jumping to conclusions.
                </span>
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
