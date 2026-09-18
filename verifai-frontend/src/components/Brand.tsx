import { Link } from "react-router-dom";

export function BrandSymbol() {
  return (
    <svg viewBox="0 0 80 80" fill="none" aria-hidden="true">
      <path
        d="M5 25V11a6 6 0 0 1 6-6h15M5 56v13a6 6 0 0 0 6 6h15"
        stroke="#0B3D91"
        strokeWidth="5"
      />
      <path
        d="M54 5h15a6 6 0 0 1 6 6v14M75 56v13a6 6 0 0 1-6 6H54"
        stroke="#D7263D"
        strokeWidth="5"
      />
      <path d="m16 26 24 35 24-35H51L40 42 29 26H16Z" fill="currentColor" />
      <path
        d="m40 10 2.5 4-1 13L40 30l-1.5-3-1-13 2.5-4Zm-13 7 4 1 7 12-3-1-9-9 1-3Zm26 0-4 1-7 12 3-1 9-9-1-3ZM33 13l3 2 3 14-2-2-5-12 1-2Zm14 0-3 2-3 14 2-2 5-12-1-2Z"
        fill="#F4B400"
      />
      <path
        d="m17 43 1.3 3.8h4l-3.2 2.4 1.2 3.8-3.3-2.4-3.3 2.4 1.3-3.8-3.3-2.4h4L17 43Zm46 0 1.3 3.8h4l-3.2 2.4 1.2 3.8-3.3-2.4-3.3 2.4 1.3-3.8-3.3-2.4h4L63 43ZM40 64l1.3 3.8h4l-3.2 2.4 1.2 3.8-3.3-2.4-3.3 2.4 1.3-3.8-3.3-2.4h4L40 64Z"
        fill="#F4B400"
      />
    </svg>
  );
}

export function Brand({ className = "" }: { className?: string }) {
  return (
    <Link className={`vf-brand ${className}`} to="/" aria-label="Verif.ai home">
      <BrandSymbol />
      <span>
        Verif<span className="vf-brand-accent">.</span>ai
      </span>
    </Link>
  );
}
