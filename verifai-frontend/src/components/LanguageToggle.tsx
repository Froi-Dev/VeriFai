import { useLanguage } from "@/i18n/useLanguage";

export function LanguageToggle() {
  const { language, setLanguage } = useLanguage();
  return (
    <div className="language-toggle" role="group" aria-label="Language / Wika">
      <button type="button" lang="fil" aria-pressed={language === "fil"} onClick={() => setLanguage("fil")}>
        Tagalog
      </button>
      <button type="button" lang="en" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>
        English
      </button>
    </div>
  );
}
