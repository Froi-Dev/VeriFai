import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, LayoutDashboard } from "lucide-react";
import { Link } from "react-router-dom";

export function HeroPreview() {
  const reduceMotion = useReducedMotion();

  return (
    <div className="hero-product-preview">
      <span className="preview-layer preview-layer-one" aria-hidden="true" />
      <span className="preview-layer preview-layer-two" aria-hidden="true" />

      <motion.div
        className="preview-window"
        initial={reduceMotion ? false : { opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.7, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="preview-toolbar">
          <div className="preview-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
          <span className="hero-preview-badge">
            <LayoutDashboard size={13} className="hero-badge-icon" />
            <span>Verif.Ai Workspace · Live Overview</span>
          </span>
          <Link to="/auth" className="preview-app-link">
            <span>Open workspace</span>
            <ArrowRight size={13} />
          </Link>
        </div>

        <div className="hero-preview-image-shell">
          <img
            src={`${import.meta.env.BASE_URL}images/dashboard-overview-preview.png`}
            alt="Verif.Ai Workspace Overview Dashboard showing scan activity, weekly charts, and recent scan verifications"
            className="hero-preview-display-img"
            width={1024}
            height={465}
            loading="eager"
          />
        </div>
      </motion.div>
    </div>
  );
}
