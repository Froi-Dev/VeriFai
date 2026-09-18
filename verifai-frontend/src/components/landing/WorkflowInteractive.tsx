import { useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { FileText, ScanSearch, BookOpen, Info } from "lucide-react";
import { Link } from "react-router-dom";

const steps = [
  {
    title: "Choose what to check",
    icon: FileText,
    summary: "Start with the content you want to understand.",
    description:
      "Use Text Analyzer for AI writing patterns, Media Analyzer for visual manipulation, or News Checker for factual claims. Each tool answers a different question.",
    note: "Checking how something was written does not tell you whether it is true.",
  },
  {
    title: "Run the analysis",
    icon: ScanSearch,
    summary: "Paste your text or upload an image.",
    description:
      "Keep the original context wherever possible. Submit the content using the selected tool and follow the progress in the assessment panel.",
    note: "Longer passages can provide more context than an isolated phrase.",
  },
  {
    title: "Review the evidence",
    icon: BookOpen,
    summary: "Read the result, its context, and its limits.",
    description:
      "Compare the assessment with the original content. For news, open the linked sources and check the dates and details. Your completed analyses are available in scan history.",
    note: "An assessment supports your judgment. It is not proof on its own.",
  },
];

export function WorkflowInteractive() {
  const [active, setActive] = useState(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const reduceMotion = useReducedMotion();
  const step = steps[active];
  const Icon = step.icon;
  return (
    <div className="verification-workflow">
      <div
        className="workflow-select"
        role="tablist"
        aria-label="How to verify content"
        aria-orientation="vertical"
      >
        {steps.map((item, index) => (
          <button
            key={item.title}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            type="button"
            role="tab"
            id={`workflow-tab-${index}`}
            aria-selected={active === index}
            aria-controls="workflow-panel"
            tabIndex={active === index ? 0 : -1}
            className={active === index ? "active" : ""}
            onClick={() => setActive(index)}
            onKeyDown={(event) => {
              const next =
                event.key === "ArrowDown"
                  ? (active + 1) % steps.length
                  : event.key === "ArrowUp"
                    ? (active + steps.length - 1) % steps.length
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? steps.length - 1
                        : null;
              if (next !== null) {
                event.preventDefault();
                setActive(next);
                buttons.current[next]?.focus();
              }
            }}
          >
            <span className="workflow-step-number">{index + 1}</span>
            <span>
              <strong>{item.title}</strong>
              <small>{item.summary}</small>
            </span>
          </button>
        ))}
      </div>
      <div
        id="workflow-panel"
        className="workflow-explanation"
        role="tabpanel"
        aria-labelledby={`workflow-tab-${active}`}
        tabIndex={0}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={active}
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.12 }}
          >
            <Icon size={30} strokeWidth={1.5} />
            <h3>{step.title}</h3>
            <p>{step.description}</p>
            <div className="workflow-note">
              <Info size={17} />
              <p>{step.note}</p>
            </div>
            <Link to="/auth" className="inline-link">
              Open your workspace
            </Link>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
