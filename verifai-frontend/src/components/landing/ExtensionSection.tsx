import { Puzzle, MousePointer2, PanelRightOpen } from "lucide-react";
import { Link } from "react-router-dom";

type ExtensionSectionProps = { onRequestAccess?: () => void };

export function ExtensionSection({ onRequestAccess }: ExtensionSectionProps) {
  return (
    <section id="extension" className="section extension-section">
      <div className="container extension-grid">
        <div className="extension-copy">
          <p className="kicker">Browser extension</p>
          <h2>
            Closer to the content.
            <br />
            Still in the works.
          </h2>
          <p>
            A browser extension is planned to bring verification into your
            reading flow. The extension package is not available yet. You can
            use all current verification tools in the web workspace.
          </p>
          {onRequestAccess ? (
            <button
              type="button"
              className="button secondary large"
              onClick={onRequestAccess}
            >
              Check extension availability
            </button>
          ) : (
            <Link className="button secondary large" to="/auth">
              Check extension availability
            </Link>
          )}
        </div>
        <div
          className="extension-roadmap"
          aria-label="Planned browser extension workflow"
        >
          <div className="extension-roadmap-heading">
            <Puzzle size={24} />
            <div>
              <strong>Verif.AI for your browser</strong>
              <span>Planned experience · not yet available</span>
            </div>
          </div>
          <div>
            <MousePointer2 size={21} />
            <p>
              <strong>Select content as you read</strong>
              <span>
                Bring the passage you want to check into your verification flow.
              </span>
            </p>
          </div>
          <div>
            <PanelRightOpen size={21} />
            <p>
              <strong>Continue in your workspace</strong>
              <span>
                Review the assessment and supporting context in one place.
              </span>
            </p>
          </div>
          <Link to="/auth" className="inline-link">
            Use the web workspace
          </Link>
        </div>
      </div>
    </section>
  );
}
