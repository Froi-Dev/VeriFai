import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Menu,
  Moon,
  Sun,
  X,
} from "lucide-react";
import {
  CapabilitiesTabs,
  ExtensionSection,
  FaqSection,
  HeroPreview,
  WorkflowInteractive,
} from "@/components/landing";

const nav = [
  ["Capabilities", "#capabilities"],
  ["How it works", "#how-it-works"],
  ["Extension", "#extension"],
  ["FAQ", "#faq"],
];

const problems = [
  [
    "01",
    "AI content spreads in seconds",
    "AI-generated posts, fake announcements, and fabricated articles spread rapidly on social feeds before readers can double-check the source.",
  ],
  [
    "02",
    "Standard detectors miss local Taglish",
    "Detectors built only for formal English get confused by Filipino code-switching, everyday campus slang, and local conversational nuance.",
  ],
  [
    "03",
    "A simple 'fake' or 'real' label isn't enough",
    "You need clear confidence scores, highlighted writing clues, and trusted news links to make an informed judgment for yourself.",
  ],
];

function Brand() {
  return (
    <a className="brand" href="#top" aria-label="Verif.Ai home">
      <span className="brand-mark" aria-hidden="true">
        <i />
        <i />
      </span>
      <span>Verif.Ai</span>
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
      initial={reduceMotion ? false : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
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

  useEffect(() => {
    const updateHeader = () => setScrolled(window.scrollY > 40);
    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });
    return () => window.removeEventListener("scroll", updateHeader);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("verifai-landing-theme", darkMode ? "dark" : "light");
    if (darkMode) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [darkMode]);

  // Handle escape key to close mobile menu
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && menu) {
        setMenu(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [menu]);

  return (
    <div id="top" className={`site ${darkMode ? "dark-mode" : ""}`}>
      {/* Sticky Navigation Header */}
      <header className={`header ${scrolled || menu ? "header-scrolled" : "header-top"}`}>
        <div className="container nav-wrap">
          <Brand />

          <nav className="desktop-nav" aria-label="Primary navigation">
            {nav.map(([label, href]) => (
              <a key={href} href={href}>
                {label}
              </a>
            ))}
          </nav>

          <div className="nav-actions">
            <button
              className="theme-toggle"
              type="button"
              onClick={() => setDarkMode((current) => !current)}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              aria-pressed={darkMode}
              title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            >
              {darkMode ? <Sun size={17} /> : <Moon size={17} />}
            </button>

            <Link className="nav-sign-in desktop-only" to="/auth">
              Sign in
            </Link>

            <Link className="button primary desktop-only" to="/auth">
              Get started <ArrowRight size={16} />
            </Link>

            <button
              className="icon-button menu-button"
              onClick={() => setMenu(!menu)}
              aria-label={menu ? "Close navigation menu" : "Open navigation menu"}
              aria-expanded={menu}
            >
              {menu ? <X size={21} /> : <Menu size={21} />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        {menu && (
          <nav className="mobile-nav" aria-label="Mobile navigation">
            {nav.map(([label, href]) => (
              <a key={href} href={href} onClick={() => setMenu(false)}>
                {label}
              </a>
            ))}
            <Link className="mobile-sign-in" to="/auth" onClick={() => setMenu(false)}>
              Sign in
            </Link>
            <Link className="button primary" to="/auth" onClick={() => setMenu(false)}>
              Get started <ArrowRight size={16} />
            </Link>
          </nav>
        )}
      </header>

      <main>
        {/* Hero Section with Interactive Neural Sandbox */}
        <section className="hero landing-hero-light">
          <div className="container hero-grid">
            <motion.div
              className="hero-copy"
              initial={reduceMotion ? false : { opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
            >
              <p className="overline">
                <span />
                <b>Philippine Digital Authenticity</b>
              </p>
              <h1>Know what is real before you share it.</h1>
              <p className="hero-lead">
                Check if articles and Taglish posts are AI-written, verify breaking news claims with trusted Philippine publishers, and spot manipulated screenshots with ease.
              </p>
              <div className="hero-actions">
                <Link className="button primary large" to="/auth">
                  Start analyzing <ArrowRight size={18} />
                </Link>
                <a className="button secondary large" href="#how-it-works">
                  See how it works
                </a>
              </div>
            </motion.div>

            {/* Authentic Workspace Overview Dashboard Preview */}
            <HeroPreview />
          </div>
        </section>

        {/* Problem Breakdown Section */}
        <section className="section problem-section">
          <div className="container">
            <Reveal className="center-heading">
              <p className="kicker">THE CHALLENGE</p>
              <h2>AI-made content is getting harder to recognize.</h2>
              <p>
                What looks authentic can still be synthetic. Simple guesswork is no longer
                enough for today's fast-moving Philippine online spaces.
              </p>
            </Reveal>

            <div className="problem-grid">
              {problems.map(([num, title, copy], index) => (
                <motion.article
                  key={num}
                  initial={reduceMotion ? false : { opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.3 }}
                  transition={{ duration: 0.5, delay: index * 0.08 }}
                >
                  <span>{num}</span>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </motion.article>
              ))}
            </div>
          </div>
        </section>

        {/* Capabilities Explorer Section */}
        <section id="capabilities" className="section capabilities-section">
          <div className="container">
            <Reveal className="center-heading">
              <p className="kicker">CAPABILITIES & HOW IT WORKS</p>
              <h2>Three focused modules with step-by-step verification.</h2>
              <p>
                Explore how each Verif.Ai tool operates from input to final score—delivering fast, transparent, and interpretable answers for everyday content.
              </p>
            </Reveal>

            <CapabilitiesTabs />
          </div>
        </section>

        {/* How It Works Section with Interactive Pipeline Visualizer */}
        <section id="how-it-works" className="section muted">
          <div className="container">
            <Reveal className="workflow-intro center-heading">
              <p className="kicker">HOW IT WORKS</p>
              <h2>Clear answers in three simple steps.</h2>
              <p>
                Verif.Ai provides likelihood scores and transparent clues so you have the right context to decide what to trust before sharing.
              </p>
            </Reveal>

            <WorkflowInteractive />
          </div>
        </section>

        {/* Browser Extension Feature Section */}
        <ExtensionSection />

        {/* Frequently Asked Questions Accordion */}
        <FaqSection />

        {/* Call to Action Section */}
        <section className="cta">
          <motion.div
            className="container cta-inner"
            initial={reduceMotion ? false : { opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.35 }}
            transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          >
            <div>
              <p className="kicker">GET STARTED</p>
              <h2>Bring clarity and context to content across the web.</h2>
            </div>
            <div>
              <p>
                Create your free account or sign in to access the full workspace,
                batch processing, and news verification history.
              </p>
              <Link className="button light large" to="/auth">
                Continue to Verif.Ai <ArrowRight size={18} />
              </Link>
            </div>
          </motion.div>
        </section>
      </main>

      {/* Footer */}
      <footer>
        <div className="container footer-top">
          <div className="footer-brand">
            <Brand />
            <p>
              Fast, friendly authenticity checks for Taglish writing, viral news stories, and screenshots—built for the Philippine online community.
            </p>
          </div>

          <div className="footer-links">
            <div>
              <strong>Platform</strong>
              <a href="#capabilities">Capabilities</a>
              <a href="#how-it-works">How it works</a>
              <a href="#extension">Browser extension</a>
              <a href="#faq">FAQ</a>
            </div>
            <div>
              <strong>Account</strong>
              <Link to="/auth">Sign in</Link>
              <Link to="/auth">Create account</Link>
            </div>
          </div>
        </div>

        <div className="container footer-bottom">
          <span>© 2026 Verif.Ai. All rights reserved.</span>
          <span>Made for the Philippine digital landscape.</span>
        </div>
      </footer>
    </div>
  );
}
