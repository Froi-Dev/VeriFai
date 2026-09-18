import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  motion,
  MotionConfig,
  useReducedMotion,
  useScroll,
  useTransform,
} from "framer-motion";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  FileImage,
  FileText,
  Link2,
  Mail,
  Menu,
  MessageCircle,
  MousePointer2,
  Newspaper,
  Plus,
  Puzzle,
  Search,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Brand, BrandSymbol } from "@/components/Brand";
import { Button } from "@/components/ui/button";

const navigation = [
  ["Ang problema", "#problem"],
  ["Ang solusyon", "#solution"],
  ["Paano gamitin", "#how-it-works"],
  ["Extension", "#extension"],
];

const questions = [
  [
    "Pwede ba ang Tagalog at Taglish?",
    "Oo. Pwedeng mag-check ng English, Filipino, at Taglish na text. Mas kapaki-pakinabang ang pagsusuri kapag may sapat na haba at konteksto ang passage.",
  ],
  [
    "Sigurado bang tama ang bawat resulta?",
    "Walang tool na laging tama. Nagbibigay ang Verif.AI ng mga palatandaan, source, at paliwanag para makatulong sa pag-check. Basahin ang mga ito bago magdesisyon—lalo na kung sensitibo o mahalaga ang impormasyon.",
  ],
  [
    "Pwede bang screenshot ang i-check?",
    "Oo. Sa News Checker, pwedeng mag-upload ng screenshot ng balita o post. Babasahin ang text sa larawan at hahanapan ng kaugnay na ulat. Para sa mismong larawan, gamitin ang Media Analyzer.",
  ],
  [
    "Saan ko makikita ang mga dati kong check?",
    "Pagka-sign in, buksan ang Scan history sa workspace. Nandoon ang mga natapos mong check. Pwede kang mag-review o magtanggal ng mga entry.",
  ],
  [
    "Available na ba ang browser extension?",
    "Oo, available para sa Chrome. Eksklusibo ito para sa mga may rehistradong account. Bisitahin ang Extension page upang i-download ang ZIP package at sundin ang gabay sa pag-install.",
  ],
];

function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.16 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

function HeroArtwork() {
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const y = useTransform(scrollYProgress, [0, 1], [0, reduced ? 0 : 70]);
  return (
    <motion.figure ref={ref} className="ph-hero-art" style={{ y }}>
      <div className="ph-art-grid" aria-hidden="true" />
      <motion.img
        className="ph-paper-stack"
        src={`${import.meta.env.BASE_URL}images/verification-stack-ph.png`}
        width="1024"
        height="1280"
        alt="Mga patong ng papel na nagpapakita ng content, pagsusuri, at source checking."
        initial={reduced ? false : { opacity: 0, y: 25 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
        fetchPriority="high"
      />
      <div className="ph-art-callouts" aria-hidden="true">
        <span>
          <FileText size={18} />
          AI content detection
        </span>
        <span>
          <Search size={18} />
          Fact verification
        </span>
        <span>
          <Link2 size={18} />
          Source analysis
        </span>
        <span>
          <ShieldCheck size={18} />
          Confidence & context
        </span>
      </div>
      <div className="ph-art-motto" aria-hidden="true">
        Mas malinaw.
        <br />
        Mas mapanuri.
        <br />
        Mas may alam.
        <i />
      </div>
      <figcaption>Illustration ng verification process</figcaption>
    </motion.figure>
  );
}

function TextVisual() {
  return (
    <div className="ph-module-visual ph-writing-visual">
      <div className="ph-preview-top">
        <span>
          <FileText size={17} /> Text Analyzer
        </span>
        <small>Halimbawa</small>
      </div>
      <div className="ph-writing-paper">
        <span className="ph-document-byline">Isang post sa feed mo</span>
        <p>
          “Sa panahon ngayon, <mark>napakahalagang maging mapanuri</mark> sa
          impormasyong nakikita natin online.{" "}
          <mark>Sa kabuuan, ang pagiging responsable</mark> ay nagsisimula sa
          bawat isa.”
        </p>
        <div className="ph-writing-lines">
          <i />
          <i />
          <i />
        </div>
      </div>
      <motion.div
        className="ph-writing-note"
        initial={{ scale: 0.94 }}
        whileInView={{ scale: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, delay: 0.25 }}
      >
        <Search size={21} />
        <div>
          <strong>May pattern. Pero hindi pa patunay.</strong>
          <p>
            Ang paulit-ulit na phrasing ay isa lang sa mga tinitingnan. Basahin
            ang buong paliwanag.
          </p>
        </div>
      </motion.div>
      <span className="ph-preview-footnote">
        Illustrative example · hindi aktuwal na analysis
      </span>
    </div>
  );
}

function NewsVisual() {
  return (
    <div className="ph-module-visual ph-news-visual">
      <div className="ph-preview-top">
        <span>
          <Newspaper size={17} /> News Checker
        </span>
        <small>Halimbawa</small>
      </div>
      <div className="ph-forwarded">
        <span>
          <MessageCircle size={17} /> Forwarded sa GC
        </span>
        <p>
          “Walang pasok bukas
          <br />
          sa buong bansa!”
        </p>
        <small>May source ba? Anong petsa?</small>
      </div>
      <svg
        className="ph-source-lines"
        viewBox="0 0 420 65"
        fill="none"
        aria-hidden="true"
      >
        <motion.path
          d="M210 0V22H70V65M210 22V65M210 22H350V65"
          stroke="#0B3D91"
          strokeWidth="1.5"
          initial={{ pathLength: 0 }}
          whileInView={{ pathLength: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.9, delay: 0.3 }}
        />
      </svg>
      <div className="ph-source-nodes">
        <div>
          <ShieldCheck />
          <strong>Orihinal na source</strong>
          <small>Sino ang naglabas?</small>
        </div>
        <div>
          <Newspaper />
          <strong>Kaugnay na ulat</strong>
          <small>May sumusuporta ba?</small>
        </div>
        <div>
          <Search />
          <strong>Petsa at lugar</strong>
          <small>Para kanino ito?</small>
        </div>
      </div>
      <span className="ph-preview-footnote">
        Sundan ang ebidensya bago mag-forward.
      </span>
    </div>
  );
}

function MediaVisual() {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 85%", "end 35%"],
  });
  const scan = useTransform(scrollYProgress, [0, 1], ["5%", "94%"]);
  return (
    <div className="ph-module-visual ph-media-visual" ref={ref}>
      <div className="ph-preview-top">
        <span>
          <FileImage size={17} /> Media Analyzer
        </span>
        <small>Halimbawa</small>
      </div>
      <div className="ph-image-scene" aria-hidden="true">
        <div className="ph-scene-sun" />
        <div className="ph-scene-mountain ph-mountain-back" />
        <div className="ph-scene-mountain" />
        <div className="ph-scene-water" />
        <div className="ph-focus-box ph-focus-one" />
        <div className="ph-focus-box ph-focus-two" />
        <motion.div
          className="ph-scan-beam"
          style={{ left: reduced ? "55%" : scan }}
        />
      </div>
      <div className="ph-media-observations">
        <span>
          <span />
          Ilaw at anino
        </span>
        <span>
          <span />
          Texture at detalye
        </span>
        <span>
          <span />
          Hindi tugmang bahagi
        </span>
      </div>
      <p className="ph-media-caption">
        May kakaiba sa larawan?
        <br />
        <strong>Tingnan natin nang mas malapitan.</strong>
      </p>
      <span className="ph-preview-footnote">
        Illustration · hindi aktuwal na analysis
      </span>
    </div>
  );
}

const modules = [
  {
    id: "text-check",
    icon: FileText,
    label: "Para sa mga salitang nababasa mo",
    title: (
      <>
        Tao ba ang sumulat?
        <br />
        <em>O may tulong ng AI?</em>
      </>
    ),
    description:
      "Hindi porke maayos ang grammar, AI na agad. Sinusuri ng Verif.AI ang mga pattern sa pagsulat para may mas malinaw kang basehan.",
    points: [
      "English, Filipino, at Taglish",
      "Mga palatandaang may kasamang paliwanag",
      "Likelihood score na may malinaw na limitasyon",
    ],
    visual: TextVisual,
  },
  {
    id: "news-check",
    icon: Newspaper,
    label: "Para sa balitang mabilis kumalat",
    title: (
      <>
        Viral na.
        <br />
        <em>Verified na ba?</em>
      </>
    ),
    description:
      "Bago maniwala sa headline o mag-forward sa GC, alamin muna kung saan ito galing. Ihambing ang claim sa mga kaugnay na ulat sa Pilipinas.",
    points: [
      "Text claims at news screenshots",
      "Mga source na pwede mong buksan",
      "Petsa, konteksto, at magkakaibang ulat",
    ],
    visual: NewsVisual,
  },
  {
    id: "image-check",
    icon: FileImage,
    label: "Para sa larawang kapani-paniwala",
    title: (
      <>
        Mukhang totoo.
        <br />
        <em>Pero buo ba ang kuwento?</em>
      </>
    ),
    description:
      "May mga larawang gawa ng AI o may binagong detalye. Tinutulungan ka ng Verif.AI na makita ang mga senyales na madaling malampasan.",
    points: [
      "Mga larawan, graphic, at screenshot",
      "Pagsusuri ng visual inconsistencies",
      "Confidence, obserbasyon, at limitasyon",
    ],
    visual: MediaVisual,
  },
];

function ContactSection() {
  const [prepared, setPrepared] = useState(false);
  function prepareEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const subject = encodeURIComponent(
      `Verif.AI — Mensahe mula kay ${data.get("name")}`,
    );
    const body = encodeURIComponent(
      `Pangalan: ${data.get("name")}\nEmail: ${data.get("email")}\n\n${data.get("message")}`,
    );
    window.location.href = `mailto:verif.ai.dev2026@gmail.com?subject=${subject}&body=${body}`;
    setPrepared(true);
  }
  return (
    <section className="ph-contact ph-section" id="contact">
      <div className="ph-shell ph-contact-grid">
        <Reveal>
          <span className="ph-section-label">Contact us</span>
          <h2>
            May tanong?
            <br />
            <em>Usap tayo.</em>
          </h2>
          <p>
            May suggestion, napansing problema, o gustong makipag-collaborate?
            Gusto naming marinig.
          </p>
          <a className="ph-email-link" href="mailto:verif.ai.dev2026@gmail.com">
            <Mail size={20} />
            verif.ai.dev2026@gmail.com
          </a>
        </Reveal>
        <Reveal delay={0.1}>
          <form className="ph-contact-form" onSubmit={prepareEmail}>
            <div className="ph-contact-fields">
              <label>
                Pangalan
                <input
                  name="name"
                  autoComplete="name"
                  placeholder="Pangalan mo"
                  required
                  maxLength={100}
                />
              </label>
              <label>
                Email
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  required
                  maxLength={254}
                />
              </label>
            </div>
            <label>
              Ano ang maitutulong namin?
              <textarea
                name="message"
                placeholder="Ikuwento mo rito."
                required
                maxLength={5000}
                rows={4}
              />
            </label>
            <Button className="ph-button ph-button-blue" type="submit">
              Buksan sa email <ArrowUpRight size={17} />
            </Button>
            <p className="ph-contact-note" role="status">
              {prepared
                ? "Nakahanda na ang mensahe para sa email app mo. Kung hindi ito bumukas, gamitin ang email address sa tabi."
                : "Magbubukas ang email app mo. Ikaw pa rin ang magpapadala."}
            </p>
          </form>
        </Reveal>
      </div>
    </section>
  );
}

export function HomePage() {
  const [menu, setMenu] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const loggedInUser = (() => {
    try {
      const stored = sessionStorage.getItem("verifai_user");
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  })();
  useEffect(() => {
    document.documentElement.classList.remove("dark");
    document.title = "Verif.AI — ’Wag basta maniwala. Siguraduhing tama.";
    const update = () => setScrolled(window.scrollY > 50);
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(false);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("keydown", escape);
    };
  }, []);

  return (
    <MotionConfig reducedMotion="user">
      <div className="ph-site" id="top" lang="fil">
        <a className="skip-link" href="#main-content">
          Pumunta sa nilalaman
        </a>
        <header
          className={`ph-header ${scrolled || menu ? "is-scrolled" : ""}`}
        >
          <div className="ph-nav">
            <Brand />
            <nav className="ph-desktop-nav" aria-label="Main navigation">
              {navigation.map(([label, href]) => (
                <a key={href} href={href}>
                  {label}
                </a>
              ))}
            </nav>
            <div className="ph-nav-actions">
              <span className="ph-nav-message">
                Para sa mas ligtas na internet
              </span>
              <Link className="ph-button ph-nav-cta" to={loggedInUser ? "/dashboard" : "/auth"}>
                {loggedInUser ? "Pumunta sa Dashboard" : "Magsimula"} <ArrowRight size={16} />
              </Link>
              <Button
                className="ph-menu"
                variant="ghost"
                aria-label={menu ? "Isara ang menu" : "Buksan ang menu"}
                aria-expanded={menu}
                aria-controls="ph-mobile-menu"
                onClick={() => setMenu(!menu)}
              >
                {menu ? <X size={23} /> : <Menu size={23} />}
              </Button>
            </div>
          </div>
          {menu && (
            <nav
              className="ph-mobile-nav"
              id="ph-mobile-menu"
              aria-label="Mobile navigation"
            >
              {navigation.map(([label, href]) => (
                <a href={href} key={href} onClick={() => setMenu(false)}>
                  {label}
                </a>
              ))}
              <a href="#faq" onClick={() => setMenu(false)}>
                FAQ
              </a>
              <a href="#contact" onClick={() => setMenu(false)}>
                Contact us
              </a>
              <Link to={loggedInUser ? "/dashboard" : "/auth"}>
                {loggedInUser ? "Pumunta sa Dashboard" : "Mag-sign in"}
              </Link>
            </nav>
          )}
        </header>
        <main id="main-content">
          <section className="ph-hero">
            <div className="ph-hero-grain" aria-hidden="true" />
            <div className="ph-shell ph-hero-grid">
              <div className="ph-hero-copy">
                <p className="ph-hero-kicker">Magbasa. Suriin. Tiyakin.</p>
                <h1>
                  ’Wag basta
                  <br />
                  maniwala.<span>Siguraduhing tama.</span>
                </h1>
                <p className="ph-hero-description">
                  A Philippine-based content validation platform that helps you
                  check AI content, news, and images—in English, Filipino, and
                  Taglish.
                </p>
                <div className="ph-hero-benefits">
                  <div>
                    <span>
                      <FileText />
                    </span>
                    <p>
                      <strong>Suriin</strong>
                      <small>
                        AI-generated
                        <br />
                        na content
                      </small>
                    </p>
                  </div>
                  <div>
                    <span>
                      <Search />
                    </span>
                    <p>
                      <strong>I-verify</strong>
                      <small>
                        Balita at
                        <br />
                        viral claims
                      </small>
                    </p>
                  </div>
                  <div>
                    <span>
                      <Users />
                    </span>
                    <p>
                      <strong>Alamin</strong>
                      <small>
                        Mas may alam
                        <br />
                        na komunidad
                      </small>
                    </p>
                  </div>
                </div>
                <div className="ph-hero-actions">
                  <Link className="ph-button" to={loggedInUser ? "/dashboard" : "/auth"}>
                    {loggedInUser ? "Pumunta sa Dashboard" : "Mag-verify na"} <ArrowRight size={20} />
                  </Link>
                  <a className="ph-learn" href="#problem">
                    Kilalanin ang Verif.AI
                  </a>
                </div>
              </div>
              <HeroArtwork />
              <div className="ph-hero-bottom">
                <span>
                  <i />
                  Gawang tao. Tamang konteksto. Tiyak na totoo.
                </span>
                <a href="#problem" aria-label="Alamin ang problema">
                  <ChevronDown size={18} />
                  Scroll para malaman
                </a>
              </div>
            </div>
          </section>

          <section className="ph-problem ph-section" id="problem">
            <div className="ph-shell">
              <Reveal className="ph-problem-heading">
                <span className="ph-section-label">Ang problema</span>
                <h2>
                  Ang bilis i-share.
                  <br />
                  <em>Ang hirap bawiin.</em>
                </h2>
                <p>
                  Isang headline. Isang screenshot. Isang “sabi nila.”
                  <br />
                  Minsan, bago pa ma-check, paniwala na ng lahat.
                </p>
              </Reveal>
              <div className="ph-problem-grid">
                <Reveal className="ph-problem-item">
                  <div
                    className="ph-problem-art ph-problem-chat"
                    aria-hidden="true"
                  >
                    <span>“Totoo ba ’to?”</span>
                    <span>“Sabi sa GC, oo.”</span>
                    <span>
                      “Share ko na.”
                      <ArrowUpRight size={15} />
                    </span>
                  </div>
                  <h3>
                    Maraming share.
                    <br />
                    Walang source.
                  </h3>
                  <p>
                    Kapag paulit-ulit mong nakikita, madaling isipin na totoo.
                    Pero hindi ebidensya ang dami ng nag-share.
                  </p>
                </Reveal>
                <Reveal className="ph-problem-item" delay={0.08}>
                  <div
                    className="ph-problem-art ph-problem-headline"
                    aria-hidden="true"
                  >
                    <span>Breaking news</span>
                    <strong>“WALANG PASOK BUKAS”</strong>
                    <small>Pero kailan pa ito?</small>
                    <i>2022</i>
                  </div>
                  <h3>
                    Totoong post.
                    <br />
                    Maling konteksto.
                  </h3>
                  <p>
                    Lumang balita, putol na quote, o larawang iba ang
                    pinanggalingan. Kapag kulang ang kuwento, iba ang dating.
                  </p>
                </Reveal>
                <Reveal className="ph-problem-item" delay={0.16}>
                  <div
                    className="ph-problem-art ph-problem-ai"
                    aria-hidden="true"
                  >
                    <FileText size={30} />
                    <div>
                      <i />
                      <i />
                      <i />
                      <i />
                    </div>
                    <span>Tao o AI?</span>
                  </div>
                  <h3>
                    Kapani-paniwala.
                    <br />
                    Pero gawa pala.
                  </h3>
                  <p>
                    Kayang gumawa ng AI ng maayos na text at makatotohanang
                    larawan. Hindi na sapat ang “mukha namang legit.”
                  </p>
                </Reveal>
              </div>
            </div>
          </section>

          <section className="ph-solution" id="solution">
            <div className="ph-shell">
              <Reveal className="ph-solution-heading">
                <span className="ph-section-label">Ang solusyon</span>
                <h2>
                  May paraan para
                  <br />
                  <em>mas makasiguro.</em>
                </h2>
                <p>
                  Iba-iba ang content. Iba-iba rin ang kailangang tingnan.
                  <br />
                  Kilalanin ang tatlong paraan ng pag-check sa Verif.AI.
                </p>
              </Reveal>
              {modules.map((module, index) => (
                <article
                  key={module.id}
                  id={module.id}
                  className={`ph-module ${index % 2 ? "ph-module-reverse" : ""}`}
                >
                  <Reveal className="ph-module-copy">
                    <span className="ph-module-label">
                      <module.icon size={18} />
                      {module.label}
                    </span>
                    <h3>{module.title}</h3>
                    <p>{module.description}</p>
                    <ul>
                      {module.points.map((point) => (
                        <li key={point}>
                          <Check size={17} />
                          {point}
                        </li>
                      ))}
                    </ul>
                  </Reveal>
                  <Reveal className="ph-module-art" delay={0.1}>
                    <module.visual />
                  </Reveal>
                </article>
              ))}
            </div>
          </section>

          <section className="ph-how ph-section" id="how-it-works">
            <div className="ph-shell">
              <Reveal className="ph-how-heading">
                <span className="ph-section-label">Paano gamitin</span>
                <h2>
                  May duda?
                  <br />
                  <em>Tatlong hakbang lang.</em>
                </h2>
                <p>
                  Hindi kailangang maging eksperto para magsimulang mag-check.
                </p>
              </Reveal>
              <ol className="ph-how-steps">
                <li>
                  <Reveal>
                    <span className="ph-step-icon">
                      <FileText size={26} />
                    </span>
                    <h3>Ilagay ang content.</h3>
                    <p>
                      I-paste ang text o claim, o i-upload ang larawan na gusto
                      mong suriin.
                    </p>
                  </Reveal>
                </li>
                <li>
                  <Reveal delay={0.1}>
                    <span className="ph-step-icon">
                      <Search size={26} />
                    </span>
                    <h3>Hayaan itong masuri.</h3>
                    <p>
                      Titingnan ng Verif.AI ang mga pattern, source, o detalye
                      ng content.
                    </p>
                  </Reveal>
                </li>
                <li>
                  <Reveal delay={0.2}>
                    <span className="ph-step-icon">
                      <ShieldCheck size={26} />
                    </span>
                    <h3>Basahin bago mag-share.</h3>
                    <p>
                      Unawain ang resulta at mga limitasyon. Ikaw pa rin ang
                      magdedesisyon.
                    </p>
                  </Reveal>
                </li>
              </ol>
              <Reveal className="ph-how-action">
                <Link className="ph-button ph-button-blue" to="/auth">
                  Subukan ang unang check <ArrowRight size={18} />
                </Link>
              </Reveal>
            </div>
          </section>

          <section className="ph-extension ph-section" id="extension">
            <div className="ph-shell ph-extension-grid">
              <Reveal>
                <span className="ph-section-label">Browser extension</span>
                <h2>
                  Habang nagba-browse,
                  <br />
                  <em>may kasamang pang-check.</em>
                </h2>
                <p>
                  Gamitin ang Verif.AI sa mismong binabasa mo.
                  Piliin ang content, buksan ang checker, at tingnan ang
                  konteksto.
                </p>
                <div className="ph-extension-status">
                  <span />
                  Available para sa Chrome · Rehistradong account lamang
                </div>
                <p className="ph-extension-note">
                  Eksklusibo para sa mga may rehistradong account.
                  Gumawa ng libreng account para ma-download at magamit ang extension.
                </p>
                <Link className="ph-underlined" to={loggedInUser ? "/dashboard/download-extension" : "/register"}>
                  {loggedInUser ? "Download at Connect" : "Gumawa ng account para ma-download"} <ArrowUpRight size={17} />
                </Link>
              </Reveal>
              <Reveal className="ph-extension-preview" delay={0.1}>
                <div className="ph-browser-bar">
                  <span>
                    <i />
                    <i />
                    <i />
                  </span>
                  <div>Habang nagbabasa online</div>
                  <Puzzle size={18} />
                </div>
                <div className="ph-browser-content">
                  <div className="ph-browser-article">
                    <span />
                    <h3>
                      May nabasa kang
                      <br />
                      parang hindi tama?
                    </h3>
                    <p>
                      <mark>Piliin ang bahaging gusto mong i-check.</mark>
                    </p>
                    <i />
                    <i />
                    <i />
                    <MousePointer2 className="ph-preview-cursor" size={29} />
                  </div>
                  <div className="ph-extension-popover">
                    <BrandSymbol />
                    <strong>Verif.AI</strong>
                    <p>Mas malinaw na konteksto, isang check lang.</p>
                    <span>
                      <Search size={14} /> Suriin ang napiling text
                    </span>
                  </div>
                </div>
                <span className="ph-preview-footnote">
                  Preview ng planong extension
                </span>
              </Reveal>
            </div>
          </section>

          <section className="ph-faq ph-section" id="faq">
            <div className="ph-shell ph-faq-grid">
              <Reveal>
                <span className="ph-section-label">FAQ</span>
                <h2>
                  Mga tanong mo,
                  <br />
                  <em>sasagutin natin.</em>
                </h2>
                <p>Para malinaw bago ka magsimula.</p>
              </Reveal>
              <div className="ph-questions">
                {questions.map(([question, answer]) => (
                  <details key={question}>
                    <summary>
                      {question}
                      <Plus size={19} />
                    </summary>
                    <p>{answer}</p>
                  </details>
                ))}
              </div>
            </div>
          </section>
          <ContactSection />
        </main>
        <footer className="ph-footer">
          <div className="ph-shell">
            <div className="ph-footer-top">
              <div>
                <Brand />
                <p>
                  Bago mag-share, siguraduhing tama.
                  <br />
                  Para sa mas may alam na Pilipinas.
                </p>
              </div>
              <div className="ph-footer-links">
                <nav aria-label="Footer navigation">
                  <a href="#problem">Ang problema</a>
                  <a href="#solution">Ang solusyon</a>
                  <a href="#how-it-works">Paano gamitin</a>
                </nav>
                <nav aria-label="Support navigation">
                  <a href="#extension">Extension</a>
                  <a href="#faq">FAQ</a>
                  <a href="#contact">Contact us</a>
                </nav>
                <nav aria-label="Account navigation">
                  {loggedInUser ? (
                    <Link to="/dashboard">Dashboard ({loggedInUser.name})</Link>
                  ) : (
                    <>
                      <Link to="/auth">Mag-sign in</Link>
                      <Link to="/register">Gumawa ng account</Link>
                    </>
                  )}
                </nav>
              </div>
            </div>
            <div className="ph-footer-bottom">
              <span>© 2026 Verif.AI. All rights reserved.</span>
              <span>
                Gawa para sa Pilipinas. <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        </footer>
      </div>
    </MotionConfig>
  );
}
