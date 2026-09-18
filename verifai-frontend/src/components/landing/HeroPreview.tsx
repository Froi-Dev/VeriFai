import { LayoutDashboard, Maximize2 } from "lucide-react";

export function HeroPreview() {
  const image = `${import.meta.env.BASE_URL}images/dashboard-overview-desktop.png`;
  return (
    <figure className="hero-product-preview">
      <div className="preview-window">
        <figcaption className="preview-toolbar">
          <span className="hero-preview-badge">
            <LayoutDashboard size={16} /> Your verification workspace
          </span>
          <a
            href={image}
            target="_blank"
            rel="noreferrer"
            aria-label="View full-size dashboard screenshot"
          >
            View full size <Maximize2 size={14} />
          </a>
        </figcaption>
        <a
          className="hero-preview-image-shell"
          href={image}
          target="_blank"
          rel="noreferrer"
          aria-label="Open dashboard screenshot in a new tab"
        >
          <img
            src={image}
            alt="Verif.Ai dashboard with analysis activity and shortcuts to the verification tools"
            className="hero-preview-display-img"
            width={1440}
            height={640}
            loading="eager"
          />
        </a>
      </div>
    </figure>
  );
}
