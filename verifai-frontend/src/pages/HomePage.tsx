import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight, Check, FileText, Menu, Moon, ScanSearch, Sun, X,
} from "lucide-react";
import { ExtensionSection } from "@/components/landing/ExtensionSection";

const nav = [
  ["Capabilities", "#capabilities"],
  ["How it works", "#how-it-works"],
  ["Browser extension", "#extension"],
];

const assetPath = (path: string) =>
  `${import.meta.env.BASE_URL}${path.replace(/^\//, "")}`;

const capabilities = [
  {
    title: "Text intelligence",
    copy: "Paste an article, message, caption, or written passage. VeriFai compares human and AI-writing likelihoods, then explains the strongest signals in language anyone can understand.",
    meta: "English · Filipino · Taglish",
    image: assetPath("/images/dashboard-text-analyzer.png"),
    imageAlt: "VeriFai Text Analyzer showing human and AI-writing likelihoods with supporting explanations",
    generated: false,
  },
  {
    title: "Image and video analysis",
    copy: "Upload one image, video, or audio file and review it beside the assessment. VeriFai highlights visual and file-level patterns associated with generated or altered media.",
    meta: "Images · Video · Audio",
    image: assetPath("/images/dashboard-media-analyzer.png"),
    imageAlt: "VeriFai Media Analyzer showing an uploaded image beside its authenticity assessment",
    generated: false,
  },
  {
    title: "Secure content handling",
    copy: "Submitted content moves through a controlled analysis pipeline. Each completed scan keeps clear processing details while uploaded material remains limited to the analysis workflow.",
    meta: "Controlled · Traceable · Private",
    image: assetPath("/images/secure-content-pipeline-v1.png"),
    imageAlt: "Illustration of documents and media passing through a protected VeriFai analysis pipeline",
    generated: true,
  },
  {
    title: "Philippine-aware models",
    copy: "VeriFai accounts for English, Filipino, and Taglish patterns, including everyday code-switching and local expressions that generic detectors may misunderstand.",
    meta: "Built with local context",
    image: assetPath("/images/ph-language-analysis-v1.png"),
    imageAlt: "English, Filipino, and Taglish signals converging into a fingerprint authenticity analysis",
    generated: true,
  },
];

const steps = [
  ["01", "Choose your content", "Paste text or upload an image or video. VeriF.ai routes it to the appropriate analysis pipeline."],
  ["02", "Run a custom model", "Our models inspect linguistic, visual, and structural signals associated with synthetic content."],
  ["03", "Review the assessment", "See the classification, confidence score, processing details, and an explanation where supported."],
];

const problems = [
  ["01", "Synthetic content moves fast", "AI-generated text and media can spread before people have time to examine where it came from."],
  ["02", "Generic detectors miss context", "Models trained elsewhere can struggle with Filipino expressions, code-switching, and Taglish writing patterns."],
  ["03", "A label is not enough", "People need confidence scores, model details, and supporting signals—not an unexplained yes or no."],
];

function Brand() {
  return (
    <a className="brand" href="#top" aria-label="VeriF.ai home">
      <span className="brand-mark" aria-hidden="true"><i /><i /></span>
      <span>VeriFai</span>
    </a>
  );
}

function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={reduceMotion ? false : { opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.65, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function HomePage() {
  const [menu, setMenu] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const savedTheme = window.localStorage.getItem("verifai-landing-theme");
    return savedTheme
      ? savedTheme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
  });
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();

  useEffect(() => {
    const updateHeader = () => setScrolled(window.scrollY > 40);
    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });
    return () => window.removeEventListener("scroll", updateHeader);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("verifai-landing-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  return (
    <div id="top" className={`site ${darkMode ? "dark-mode" : ""}`}>
      <header className={`header ${scrolled || menu ? "header-scrolled" : "header-top"}`}>
        <div className="container nav-wrap">
          <Brand />
          <nav className="desktop-nav" aria-label="Primary navigation">
            {nav.map(([label, href]) => <a key={href} href={href}>{label}</a>)}
          </nav>
          <div className="nav-actions">
            <button
              className="theme-toggle"
              type="button"
              onClick={() => setDarkMode((current) => !current)}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              aria-pressed={darkMode}
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <Link className="nav-sign-in desktop-only" to="/auth">Sign in</Link>
            <Link className="button primary desktop-only" to="/auth">
              Get started <ArrowRight size={16} />
            </Link>
            <button className="icon-button menu-button" onClick={() => setMenu(!menu)}
              aria-label={menu ? "Close navigation" : "Open navigation"} aria-expanded={menu}>
              {menu ? <X size={21} /> : <Menu size={21} />}
            </button>
          </div>
        </div>
        {menu && (
          <nav className="mobile-nav" aria-label="Mobile navigation">
            {nav.map(([label, href]) => <a key={href} href={href} onClick={() => setMenu(false)}>{label}</a>)}
            <Link className="mobile-sign-in" to="/auth" onClick={() => setMenu(false)}>Sign in</Link>
            <Link className="button primary" to="/auth" onClick={() => setMenu(false)}>
              Get started <ArrowRight size={16} />
            </Link>
          </nav>
        )}
      </header>

      <main>
        <section className="hero landing-hero-light">
          <div className="container hero-grid">
            <motion.div
              className="hero-copy"
              initial={reduceMotion ? false : { opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            >
              <p className="overline"><span /><b>Detect - Authenticate</b></p>
              <h1>Know what is real before you share it.</h1>
              <p className="hero-lead">Analyze text, images, video, and audio for signals associated with AI-generated or altered content.</p>
              <div className="hero-actions">
                <Link className="button primary large" to="/auth">
                  Start analyzing <ArrowRight size={18} />
                </Link>
                <a className="button secondary large" href="#how-it-works">See how it works</a>
              </div>
            </motion.div>
            <div className="hero-product-preview">
              <span className="preview-layer preview-layer-one" aria-hidden="true" />
              <span className="preview-layer preview-layer-two" aria-hidden="true" />
              <div className="preview-window">
                <div className="preview-toolbar">
                  <span className="preview-dots" aria-hidden="true"><i /><i /><i /></span>
                  <span>VeriFai workspace</span>
                  <Link to="/auth">Open app <ArrowRight size={13} /></Link>
                </div>
                <img
                  src={assetPath("/images/dashboard-overview-desktop.png")}
                  alt="VeriFai dashboard showing weekly scan activity and recent analyses"
                />
              </div>
            </div>
          </div>
        </section>

        <section className="section problem-section">
          <div className="container">
            <Reveal className="center-heading">
              <p className="kicker">PROBLEM</p>
              <h2>AI-made content is getting harder to recognize.</h2>
              <p>What looks familiar can still be synthetic. Guesswork is no longer a reliable way to assess digital content.</p>
            </Reveal>
            <div className="problem-grid">
              {problems.map(([num, title, copy], index) => (
                <motion.article
                  key={num}
                  initial={reduceMotion ? false : { opacity: 0, y: 28 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.35 }}
                  transition={{ duration: 0.55, delay: index * 0.09 }}
                >
                  <span>{num}</span>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </motion.article>
              ))}
            </div>
          </div>
        </section>

        <section id="capabilities" className="section">
          <div className="container">
            <Reveal className="section-heading split-heading">
              <div><p className="kicker">SOLUTION</p><h2>Analyze content in the form it reaches you.</h2></div>
              <p>Each content type is handled by a dedicated model pipeline, designed to surface the signals that matter for that medium.</p>
            </Reveal>
            <div className="feature-list">
              {capabilities.map(({ title, copy, meta, image, imageAlt, generated }, index) => (
                <motion.article
                  className="feature-row"
                  key={title}
                  initial={reduceMotion ? false : { opacity: 0, y: 32 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.18 }}
                  transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                >
                  <div className="feature-copy">
                    <span className="feature-number">0{index + 1}</span>
                    <p className="feature-meta">{meta}</p>
                    <h3>{title}</h3>
                    <p>{copy}</p>
                  </div>
                  <div className={`feature-image ${generated ? "generated-feature-image" : ""}`}>
                    <div className="feature-image-bar">
                      <span><i /><i /><i /></span>
                      <small>{title}</small>
                    </div>
                    <img src={image} alt={imageAlt} />
                  </div>
                </motion.article>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="section muted">
          <div className="container">
            <Reveal className="workflow-intro center-heading">
              <p className="kicker">HOW IT WORKS</p>
              <h2>From upload to assessment in three clear steps.</h2>
              <p>VeriF.ai reports likelihood—not truth. Results are designed to support human judgment, not replace it.</p>
            </Reveal>
            <div className="workflow-grid">
              <div className="steps">
                {steps.map(([num, title, copy], index) => (
                  <motion.article
                    className="step"
                    key={num}
                    initial={reduceMotion ? false : { opacity: 0, x: -28 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, amount: 0.45 }}
                    transition={{ duration: 0.55, delay: index * 0.08, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <span>{num}</span><div><h3>{title}</h3><p>{copy}</p></div>
                  </motion.article>
                ))}
              </div>
              <motion.div
                className="workflow-visual glass"
                initial={reduceMotion ? false : { opacity: 0, y: 28, scale: 0.97 }}
                whileInView={{ opacity: 1, y: 0, scale: 1 }}
                viewport={{ once: true, amount: 0.25 }}
                transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              >
                <span className="mockup-label">Concept preview</span>
                <div className="workflow-bar"><i /><i /><i /><span>New analysis</span></div>
                <div className="drop-zone">
                  <span><FileText size={22} /></span>
                  <strong>Drop content to analyze</strong>
                  <small>Text, image, or video</small>
                </div>
                <div className="process-row">
                  <span className="process-done"><Check size={15} /></span>
                  <div><strong>Content received</strong><small>Routing to Text Model v1.4</small></div>
                  <span>Complete</span>
                </div>
                <div className="process-row">
                  <span className="process-active"><ScanSearch size={15} /></span>
                  <div><strong>Analyzing signals</strong><small>Language detected: Taglish</small></div>
                  <span>Processing</span>
                </div>
                <div className="process-progress"><i /></div>
              </motion.div>
            </div>
          </div>
        </section>

        <ExtensionSection onRequestAccess={() => navigate("/auth")} />

        <section className="cta">
          <motion.div
            className="container cta-inner"
            initial={reduceMotion ? false : { opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.35 }}
            transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          >
            <div><p className="kicker">START ANALYZING</p><h2>Bring more context to the content you encounter online.</h2></div>
            <div><p>Create your VeriF.ai account or sign in to continue to the analysis workspace.</p>
              <Link className="button light large" to="/auth">Continue to VeriF.ai <ArrowRight size={18} /></Link>
            </div>
          </motion.div>
        </section>
      </main>

      <footer>
        <div className="container footer-top">
          <div className="footer-brand"><Brand /><p>Confidence-based authenticity analysis for text, images, and video—available on the web and in your browser.</p></div>
          <div className="footer-links">
            <div><strong>Platform</strong><a href="#capabilities">Capabilities</a><a href="#how-it-works">How it works</a><a href="#extension">Browser extension</a></div>
            <div><strong>Account</strong><Link to="/auth">Sign in or create account</Link></div>
          </div>
        </div>
        <div className="container footer-bottom"><span>© 2026 VeriF.ai. All rights reserved.</span><span>Made for the Philippine digital landscape.</span></div>
      </footer>
    </div>
  );
}
