import { T } from "@/i18n/LanguageContext";
import { useLanguage } from "@/i18n/useLanguage";
import { LanguageToggle } from "@/components/LanguageToggle";
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
  const { t } = useLanguage();
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
        alt={t("Mga patong ng papel na nagpapakita ng content, pagsusuri, at source checking.")}
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
      <div className="ph-art-motto" aria-hidden="true"><T>{"Mas malinaw."}</T><br /><T>{"Mas mapanuri."}</T><br /><T>{"Mas may alam."}</T><i />
      </div>
      <figcaption><T>{"Illustration ng verification process"}</T></figcaption>
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
        <small><T>{"Halimbawa"}</T></small>
      </div>
      <div className="ph-writing-paper">
        <span className="ph-document-byline"><T>{"Isang post sa feed mo"}</T></span>
        <p><T>{"“Sa panahon ngayon, "}</T><mark><T>{"napakahalagang maging mapanuri"}</T></mark><T>{" sa impormasyong nakikita natin online."}</T>{" "}
          <mark><T>{"Sa kabuuan, ang pagiging responsable"}</T></mark><T>{" ay nagsisimula sa bawat isa.”"}</T></p>
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
          <strong><T>{"May pattern. Pero hindi pa patunay."}</T></strong>
          <p><T>{"Ang paulit-ulit na phrasing ay isa lang sa mga tinitingnan. Basahin ang buong paliwanag."}</T></p>
        </div>
      </motion.div>
      <span className="ph-preview-footnote"><T>{"Illustrative example · hindi aktuwal na analysis"}</T></span>
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
        <small><T>{"Halimbawa"}</T></small>
      </div>
      <div className="ph-forwarded">
        <span>
          <MessageCircle size={17} /><T>{" Forwarded sa GC"}</T></span>
        <p><T>{"“Walang pasok bukas"}</T><br /><T>{"sa buong bansa!”"}</T></p>
        <small><T>{"May source ba? Anong petsa?"}</T></small>
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
          <strong><T>{"Orihinal na source"}</T></strong>
          <small><T>{"Sino ang naglabas?"}</T></small>
        </div>
        <div>
          <Newspaper />
          <strong><T>{"Kaugnay na ulat"}</T></strong>
          <small><T>{"May sumusuporta ba?"}</T></small>
        </div>
        <div>
          <Search />
          <strong><T>{"Petsa at lugar"}</T></strong>
          <small><T>{"Para kanino ito?"}</T></small>
        </div>
      </div>
      <span className="ph-preview-footnote"><T>{"Sundan ang ebidensya bago mag-forward."}</T></span>
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
        <small><T>{"Halimbawa"}</T></small>
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
          <span /><T>{"Ilaw at anino"}</T></span>
        <span>
          <span /><T>{"Texture at detalye"}</T></span>
        <span>
          <span /><T>{"Hindi tugmang bahagi"}</T></span>
      </div>
      <p className="ph-media-caption"><T>{"May kakaiba sa larawan?"}</T><br />
        <strong><T>{"Tingnan natin nang mas malapitan."}</T></strong>
      </p>
      <span className="ph-preview-footnote"><T>{"Illustration · hindi aktuwal na analysis"}</T></span>
    </div>
  );
}

const modules = [
  {
    id: "text-check",
    icon: FileText,
    label: "Para sa mga salitang nababasa mo",
    title: (
      <><T>{"Tao ba ang sumulat?"}</T><br />
        <em><T>{"O may tulong ng AI?"}</T></em>
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
      <><T>{"Viral na."}</T><br />
        <em><T>{"Verified na ba?"}</T></em>
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
      <><T>{"Mukhang totoo."}</T><br />
        <em><T>{"Pero buo ba ang kuwento?"}</T></em>
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
  const { t } = useLanguage();
  const [prepared, setPrepared] = useState(false);
  function prepareEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const subject = encodeURIComponent(
      `Verif.AI — ${t("Mensahe mula kay")} ${data.get("name")}`,
    );
    const body = encodeURIComponent(
      `${t("Pangalan")}: ${data.get("name")}\nEmail: ${data.get("email")}\n\n${data.get("message")}`,
    );
    window.location.href = `mailto:verif.ai.dev2026@gmail.com?subject=${subject}&body=${body}`;
    setPrepared(true);
  }
  return (
    <section className="ph-contact ph-section" id="contact">
      <div className="ph-shell ph-contact-grid">
        <Reveal>
          <span className="ph-section-label">Contact us</span>
          <h2><T>{"May tanong?"}</T><br />
            <em><T>{"Usap tayo."}</T></em>
          </h2>
          <p><T>{"May suggestion, napansing problema, o gustong makipag-collaborate? Gusto naming marinig."}</T></p>
          <a className="ph-email-link" href="mailto:verif.ai.dev2026@gmail.com">
            <Mail size={20} />
            verif.ai.dev2026@gmail.com
          </a>
        </Reveal>
        <Reveal delay={0.1}>
          <form className="ph-contact-form" onSubmit={prepareEmail}>
            <div className="ph-contact-fields">
              <label><T>{"Pangalan"}</T><input
                  name="name"
                  autoComplete="name"
                  placeholder={t("Pangalan mo")}
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
            <label><T>{"Ano ang maitutulong namin?"}</T><textarea
                name="message"
                placeholder={t("Ikuwento mo rito.")}
                required
                maxLength={5000}
                rows={4}
              />
            </label>
            <Button className="ph-button ph-button-blue" type="submit"><T>{"Buksan sa email "}</T><ArrowUpRight size={17} />
            </Button>
            <p className="ph-contact-note" role="status">
              {prepared
                ? t("Nakahanda na ang mensahe para sa email app mo. Kung hindi ito bumukas, gamitin ang email address sa tabi.")
                : t("Magbubukas ang email app mo. Ikaw pa rin ang magpapadala.")}
            </p>
          </form>
        </Reveal>
      </div>
    </section>
  );
}

export function HomePage() {
  const { language, t } = useLanguage();
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

  useEffect(() => {
    document.title = t("Verif.AI — ’Wag basta maniwala. Siguraduhing tama.");
  }, [t]);

  return (
    <MotionConfig reducedMotion="user">
      <div className="ph-site" id="top" lang={language}>
        <a className="skip-link" href="#main-content"><T>{"Pumunta sa nilalaman"}</T></a>
        <header
          className={`ph-header ${scrolled || menu ? "is-scrolled" : ""}`}
        >
          <div className="ph-nav">
            <Brand />
            <nav className="ph-desktop-nav" aria-label="Main navigation">
              {navigation.map(([label, href]) => (
                <a key={href} href={href}>
                  {t(label)}
                </a>
              ))}
            </nav>
            <div className="ph-nav-actions">
              <LanguageToggle />
              <span className="ph-nav-message"><T>{"Para sa mas ligtas na internet"}</T></span>
              <Link className="ph-button ph-nav-cta" to={loggedInUser ? "/dashboard" : "/auth"}>
                {loggedInUser ? t("Pumunta sa Dashboard") : t("Magsimula")} <ArrowRight size={16} />
              </Link>
              <Button
                className="ph-menu"
                variant="ghost"
                aria-label={menu ? t("Isara ang menu") : t("Buksan ang menu")}
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
                  {t(label)}
                </a>
              ))}
              <a href="#faq" onClick={() => setMenu(false)}>
                FAQ
              </a>
              <a href="#contact" onClick={() => setMenu(false)}>
                Contact us
              </a>
              <Link to={loggedInUser ? "/dashboard" : "/auth"}>
                {loggedInUser ? t("Pumunta sa Dashboard") : t("Mag-sign in")}
              </Link>
            </nav>
          )}
        </header>
        <main id="main-content">
          <section className="ph-hero">
            <div className="ph-hero-grain" aria-hidden="true" />
            <div className="ph-shell ph-hero-grid">
              <div className="ph-hero-copy">
                <p className="ph-hero-kicker"><T>{"Magbasa. Suriin. Tiyakin."}</T></p>
                <h1><T>{"’Wag basta"}</T><br /><T>{"maniwala."}</T><span><T>{"Siguraduhing tama."}</T></span>
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
                      <strong><T>{"Suriin"}</T></strong>
                      <small>
                        AI-generated
                        <br /><T>{"na content"}</T></small>
                    </p>
                  </div>
                  <div>
                    <span>
                      <Search />
                    </span>
                    <p>
                      <strong><T>{"I-verify"}</T></strong>
                      <small><T>{"Balita at"}</T><br />
                        viral claims
                      </small>
                    </p>
                  </div>
                  <div>
                    <span>
                      <Users />
                    </span>
                    <p>
                      <strong><T>{"Alamin"}</T></strong>
                      <small><T>{"Mas may alam"}</T><br /><T>{"na komunidad"}</T></small>
                    </p>
                  </div>
                </div>
                <div className="ph-hero-actions">
                  <Link className="ph-button" to={loggedInUser ? "/dashboard" : "/auth"}>
                    {loggedInUser ? t("Pumunta sa Dashboard") : t("Mag-verify na")} <ArrowRight size={20} />
                  </Link>
                  <a className="ph-learn" href="#problem"><T>{"Kilalanin ang Verif.AI"}</T></a>
                </div>
              </div>
              <HeroArtwork />
              <div className="ph-hero-bottom">
                <span>
                  <i /><T>{"Gawang tao. Tamang konteksto. Tiyak na totoo."}</T></span>
                <a href="#problem" aria-label={t("Alamin ang problema")}>
                  <ChevronDown size={18} /><T>{"Scroll para malaman"}</T></a>
              </div>
            </div>
          </section>

          <section className="ph-problem ph-section" id="problem">
            <div className="ph-shell">
              <Reveal className="ph-problem-heading">
                <span className="ph-section-label"><T>{"Ang problema"}</T></span>
                <h2><T>{"Ang bilis i-share."}</T><br />
                  <em><T>{"Ang hirap bawiin."}</T></em>
                </h2>
                <p><T>{"Isang headline. Isang screenshot. Isang “sabi nila.”"}</T><br /><T>{"Minsan, bago pa ma-check, paniwala na ng lahat."}</T></p>
              </Reveal>
              <div className="ph-problem-grid">
                <Reveal className="ph-problem-item">
                  <div
                    className="ph-problem-art ph-problem-chat"
                    aria-hidden="true"
                  >
                    <span><T>{"“Totoo ba ’to?”"}</T></span>
                    <span><T>{"“Sabi sa GC, oo.”"}</T></span>
                    <span><T>{"“Share ko na.”"}</T><ArrowUpRight size={15} />
                    </span>
                  </div>
                  <h3><T>{"Maraming share."}</T><br /><T>{"Walang source."}</T></h3>
                  <p><T>{"Kapag paulit-ulit mong nakikita, madaling isipin na totoo. Pero hindi ebidensya ang dami ng nag-share."}</T></p>
                </Reveal>
                <Reveal className="ph-problem-item" delay={0.08}>
                  <div
                    className="ph-problem-art ph-problem-headline"
                    aria-hidden="true"
                  >
                    <span>Breaking news</span>
                    <strong><T>{"“WALANG PASOK BUKAS”"}</T></strong>
                    <small><T>{"Pero kailan pa ito?"}</T></small>
                    <i>2022</i>
                  </div>
                  <h3><T>{"Totoong post."}</T><br /><T>{"Maling konteksto."}</T></h3>
                  <p><T>{"Lumang balita, putol na quote, o larawang iba ang pinanggalingan. Kapag kulang ang kuwento, iba ang dating."}</T></p>
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
                    <span><T>{"Tao o AI?"}</T></span>
                  </div>
                  <h3><T>{"Kapani-paniwala."}</T><br /><T>{"Pero gawa pala."}</T></h3>
                  <p><T>{"Kayang gumawa ng AI ng maayos na text at makatotohanang larawan. Hindi na sapat ang “mukha namang legit.”"}</T></p>
                </Reveal>
              </div>
            </div>
          </section>

          <section className="ph-solution" id="solution">
            <div className="ph-shell">
              <Reveal className="ph-solution-heading">
                <span className="ph-section-label"><T>{"Ang solusyon"}</T></span>
                <h2><T>{"May paraan para"}</T><br />
                  <em><T>{"mas makasiguro."}</T></em>
                </h2>
                <p><T>{"Iba-iba ang content. Iba-iba rin ang kailangang tingnan."}</T><br /><T>{"Kilalanin ang tatlong paraan ng pag-check sa Verif.AI."}</T></p>
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
                      {t(module.label)}
                    </span>
                    <h3>{module.title}</h3>
                    <p>{t(module.description)}</p>
                    <ul>
                      {module.points.map((point) => (
                        <li key={point}>
                          <Check size={17} />
                          {t(point)}
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
                <span className="ph-section-label"><T>{"Paano gamitin"}</T></span>
                <h2><T>{"May duda?"}</T><br />
                  <em><T>{"Tatlong hakbang lang."}</T></em>
                </h2>
                <p><T>{"Hindi kailangang maging eksperto para magsimulang mag-check."}</T></p>
              </Reveal>
              <ol className="ph-how-steps">
                <li>
                  <Reveal>
                    <span className="ph-step-icon">
                      <FileText size={26} />
                    </span>
                    <h3><T>{"Ilagay ang content."}</T></h3>
                    <p><T>{"I-paste ang text o claim, o i-upload ang larawan na gusto mong suriin."}</T></p>
                  </Reveal>
                </li>
                <li>
                  <Reveal delay={0.1}>
                    <span className="ph-step-icon">
                      <Search size={26} />
                    </span>
                    <h3><T>{"Hayaan itong masuri."}</T></h3>
                    <p><T>{"Titingnan ng Verif.AI ang mga pattern, source, o detalye ng content."}</T></p>
                  </Reveal>
                </li>
                <li>
                  <Reveal delay={0.2}>
                    <span className="ph-step-icon">
                      <ShieldCheck size={26} />
                    </span>
                    <h3><T>{"Basahin bago mag-share."}</T></h3>
                    <p><T>{"Unawain ang resulta at mga limitasyon. Ikaw pa rin ang magdedesisyon."}</T></p>
                  </Reveal>
                </li>
              </ol>
              <Reveal className="ph-how-action">
                <Link className="ph-button ph-button-blue" to="/auth"><T>{"Subukan ang unang check "}</T><ArrowRight size={18} />
                </Link>
              </Reveal>
            </div>
          </section>

          <section className="ph-extension ph-section" id="extension">
            <div className="ph-shell ph-extension-grid">
              <Reveal>
                <span className="ph-section-label">Browser extension</span>
                <h2><T>{"Habang nagba-browse,"}</T><br />
                  <em><T>{"may kasamang pang-check."}</T></em>
                </h2>
                <p><T>{"Gamitin ang Verif.AI sa mismong binabasa mo. Piliin ang content, buksan ang checker, at tingnan ang konteksto."}</T></p>
                <div className="ph-extension-status">
                  <span /><T>{"Available para sa Chrome · Rehistradong account lamang"}</T></div>
                <p className="ph-extension-note"><T>{"Eksklusibo para sa mga may rehistradong account. Gumawa ng libreng account para ma-download at magamit ang extension."}</T></p>
                <Link className="ph-underlined" to={loggedInUser ? "/dashboard/download-extension" : "/register"}>
                  {loggedInUser ? t("Download at Connect") : t("Gumawa ng account para ma-download")} <ArrowUpRight size={17} />
                </Link>
              </Reveal>
              <Reveal className="ph-extension-preview" delay={0.1}>
                <div className="ph-browser-bar">
                  <span>
                    <i />
                    <i />
                    <i />
                  </span>
                  <div><T>{"Habang nagbabasa online"}</T></div>
                  <Puzzle size={18} />
                </div>
                <div className="ph-browser-content">
                  <div className="ph-browser-article">
                    <span />
                    <h3><T>{"May nabasa kang"}</T><br /><T>{"parang hindi tama?"}</T></h3>
                    <p>
                      <mark><T>{"Piliin ang bahaging gusto mong i-check."}</T></mark>
                    </p>
                    <i />
                    <i />
                    <i />
                    <MousePointer2 className="ph-preview-cursor" size={29} />
                  </div>
                  <div className="ph-extension-popover">
                    <BrandSymbol />
                    <strong>Verif.AI</strong>
                    <p><T>{"Mas malinaw na konteksto, isang check lang."}</T></p>
                    <span>
                      <Search size={14} /><T>{" Suriin ang napiling text"}</T></span>
                  </div>
                </div>
                <span className="ph-preview-footnote"><T>{"Preview ng planong extension"}</T></span>
              </Reveal>
            </div>
          </section>

          <section className="ph-faq ph-section" id="faq">
            <div className="ph-shell ph-faq-grid">
              <Reveal>
                <span className="ph-section-label">FAQ</span>
                <h2><T>{"Mga tanong mo,"}</T><br />
                  <em><T>{"sasagutin natin."}</T></em>
                </h2>
                <p><T>{"Para malinaw bago ka magsimula."}</T></p>
              </Reveal>
              <div className="ph-questions">
                {questions.map(([question, answer]) => (
                  <details key={question}>
                    <summary>
                      {t(question)}
                      <Plus size={19} />
                    </summary>
                    <p>{t(answer)}</p>
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
                <p><T>{"Bago mag-share, siguraduhing tama."}</T><br /><T>{"Para sa mas may alam na Pilipinas."}</T></p>
              </div>
              <div className="ph-footer-links">
                <nav aria-label="Footer navigation">
                  <a href="#problem"><T>{"Ang problema"}</T></a>
                  <a href="#solution"><T>{"Ang solusyon"}</T></a>
                  <a href="#how-it-works"><T>{"Paano gamitin"}</T></a>
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
                      <Link to="/auth"><T>{"Mag-sign in"}</T></Link>
                      <Link to="/register"><T>{"Gumawa ng account"}</T></Link>
                    </>
                  )}
                </nav>
              </div>
            </div>
            <div className="ph-footer-bottom">
              <span>© 2026 Verif.AI. All rights reserved.</span>
              <span><T>{"Gawa para sa Pilipinas. "}</T><i />
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
