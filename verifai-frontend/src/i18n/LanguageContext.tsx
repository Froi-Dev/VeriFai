import { useCallback, useEffect, useState, type ReactNode } from "react";
import { english } from "./en";
import { LanguageContext, useLanguage, type Language } from "./useLanguage";

const storageKey = "verifai_language";

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => {
    try {
      return localStorage.getItem(storageKey) === "en" ? "en" : "fil";
    } catch {
      return "fil";
    }
  });

  useEffect(() => {
    document.documentElement.lang = language;
    try {
      localStorage.setItem(storageKey, language);
    } catch {
      // The toggle still works when browser storage is unavailable.
    }
  }, [language]);

  const t = useCallback((text: string) => {
    if (language === "fil") return text;
    const key = text.replace(/\s+/g, " ").trim();
    const translated = english[key];
    if (!translated) return text;
    return `${text.match(/^\s*/)?.[0] ?? ""}${translated}${text.match(/\s*$/)?.[0] ?? ""}`;
  }, [language]);

  return <LanguageContext.Provider value={{ language, setLanguage, t }}>{children}</LanguageContext.Provider>;
}

// This renders a text node, preserving existing typography and inline markup.
export function T({ children }: { children: string }) {
  const { t } = useLanguage();
  return t(children);
}
