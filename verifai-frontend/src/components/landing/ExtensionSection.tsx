import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Check,
  FileText,
  Image as ImageIcon,
  MousePointerClick,
  Puzzle,
  ScanSearch,
} from "lucide-react";

type ExtensionSectionProps = {
  onRequestAccess: () => void;
};

export function ExtensionSection({ onRequestAccess }: ExtensionSectionProps) {
  const reduceMotion = useReducedMotion();

  return (
    <section id="extension" className="section extension-section">
      <div className="container extension-grid">
        <motion.div
          className="extension-copy"
          initial={reduceMotion ? false : { opacity: 0, x: -32 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
        >
          <p className="kicker">BROWSER EXTENSION</p>
          <h2>Check content without leaving the page.</h2>
          <p>
            Use Verif.Ai from the browser for quick, in-context checks, then move to
            the web app when you need a fuller analysis workspace.
          </p>
          <ul>
            <li><Check size={16} /> Access the same confidence-based assessment approach</li>
            <li><Check size={16} /> Analyze text and media closer to where you encounter it</li>
            <li><Check size={16} /> Review clear results designed to support human judgment</li>
          </ul>
          <button className="button primary large" onClick={onRequestAccess}>
            Continue to Verif.Ai <ArrowRight size={18} />
          </button>
        </motion.div>

        <motion.div
          className="extension-visual"
          aria-label="Concept preview of the Verif.Ai browser extension"
          initial={reduceMotion ? false : { opacity: 0, y: 28, scale: 0.98 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, amount: 0.25 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="mockup-label">Concept preview</span>
          <div className="browser-frame">
            <div className="browser-toolbar">
              <span className="window-dots"><i /><i /><i /></span>
              <span className="browser-address">article.example.ph</span>
              <span className="extension-toolbar-icon"><Puzzle size={15} /></span>
            </div>
            <div className="browser-page">
              <div className="browser-article" aria-hidden="true">
                <span className="article-label">LATEST STORY</span>
                <i className="article-title" />
                <i /><i /><i className="selected-copy" /><i /><i />
                <div className="article-media"><ImageIcon size={20} /></div>
              </div>
              <div className="extension-panel">
                <div className="extension-panel-head">
                  <span><Puzzle size={17} /> Verif.Ai</span>
                  <small>Browser extension</small>
                </div>
                <div className="extension-selection">
                  <span><MousePointerClick size={15} /></span>
                  <div><strong>Content selected</strong><small>Text · Taglish detected</small></div>
                </div>
                <div className="extension-panel-action"><ScanSearch size={16} /> Analyze selection</div>
                <p>Results open with classification, confidence, and scan details.</p>
                <div className="extension-surface-link">
                  <FileText size={14} />
                  <span>Continue in the web app</span>
                  <ArrowRight size={14} />
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
