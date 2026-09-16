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
import { Link } from "react-router-dom";

type ExtensionSectionProps = {
  onRequestAccess?: () => void;
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
            Use Verif.Ai directly from Chrome, Edge, or Brave for quick, in-context checks, then move to
            the full web workspace when you need deeper investigation.
          </p>
          <ul>
            <li>
              <Check size={16} /> Check articles and social posts right inside your browser
            </li>
            <li>
              <Check size={16} /> Highlight any Taglish, Filipino, or English text for an instant check
            </li>
            <li>
              <Check size={16} /> Get clear likelihood percentages and helpful writing clues
            </li>
          </ul>

          {onRequestAccess ? (
            <button
              type="button"
              className="button primary large"
              onClick={onRequestAccess}
            >
              Get extension access <ArrowRight size={18} />
            </button>
          ) : (
            <Link className="button primary large" to="/auth">
              Get extension access <ArrowRight size={18} />
            </Link>
          )}
        </motion.div>

        <motion.div
          className="extension-visual"
          aria-label="Interactive concept preview of the Verif.Ai browser extension"
          initial={reduceMotion ? false : { opacity: 0, y: 28, scale: 0.98 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, amount: 0.25 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="mockup-label">Live Concept Preview</span>
          <div className="browser-frame">
            <div className="browser-toolbar">
              <span className="window-dots">
                <i />
                <i />
                <i />
              </span>
              <span className="browser-address">news.portal.ph/article/digital-rights</span>
              <span className="extension-toolbar-icon" title="Verif.Ai extension active">
                <Puzzle size={15} />
              </span>
            </div>

            <div className="browser-page">
              <div className="browser-article" aria-hidden="true">
                <span className="article-label">VERIFIED JOURNALISM</span>
                <i className="article-title" />
                <i />
                <i />
                <i className="selected-copy" />
                <i />
                <i />
                <div className="article-media">
                  <ImageIcon size={20} />
                </div>
              </div>

              <div className="extension-panel">
                <div className="extension-panel-head">
                  <span>
                    <Puzzle size={17} /> Verif.Ai
                  </span>
                  <small>Active v2.4</small>
                </div>

                <div className="extension-selection">
                  <span>
                    <MousePointerClick size={15} />
                  </span>
                  <div>
                    <strong>Selected Passage</strong>
                    <small>Text · Taglish detected</small>
                  </div>
                </div>

                <div className="extension-panel-action">
                  <ScanSearch size={16} /> Instant Scan Active
                </div>

                <p>94% Likely Human · Natural Taglish conversation detected.</p>

                <Link to="/auth" className="extension-surface-link">
                  <FileText size={14} />
                  <span>Open in Full Workspace</span>
                  <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
