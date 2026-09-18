import { useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, FileImage, FileText, Menu, Newspaper, ShieldCheck, UserRound, X } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Brand } from "@/components/Brand";
import type { Scanner } from "@/services/guest";
import "@/pages/guest.css";

export const trialScanners = [
  { key: "text" as const, label: "AI Text Scanner", icon: FileText },
  { key: "image" as const, label: "AI Image Scanner", icon: FileImage },
  { key: "news" as const, label: "Fake News / Fact Checker", icon: Newspaper },
];

type TrialLayoutProps = {
  page: "consent" | "scanner";
  children: ReactNode;
  scanner?: Scanner;
  onScannerChange?: (scanner: Scanner) => void;
  busy?: boolean;
};

export function TrialLayout({ page, children, scanner, onScannerChange, busy }: TrialLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();
  const title = page === "consent" ? "Guest consent" : trialScanners.find(item => item.key === scanner)?.label;

  const user = (() => {
    try {
      const stored = sessionStorage.getItem("verifai_user");
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  })();

  const hasGuestToken = typeof window !== "undefined" && Boolean(localStorage.getItem("verifai_guest"));

  useEffect(() => {
    if (user) {
      navigate("/dashboard", { replace: true });
    }
  }, [user, navigate]);

  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · Verif.AI`;
    return () => { document.title = previous; };
  }, [title]);

  useEffect(() => {
    if (!sidebarOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setSidebarOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [sidebarOpen]);

  return (
    <div className="dashboard-shell dashboard-layout trial-layout">
      {sidebarOpen && <button className="mobile-sidebar-backdrop" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
      <aside className={`dashboard-sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-head">
          <Brand className="dashboard-brand" />
          <button className="sidebar-close" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}><X size={18} /></button>
        </div>
        <nav className="sidebar-nav" aria-label="Trial navigation">
          <p>{page === "consent" || (!hasGuestToken && !user) ? "Get started" : "Guest workspace"}</p>
          {page === "consent" ? (
            <button className="active" aria-current="page">
              <ShieldCheck size={18} /><span>Guest consent</span>
            </button>
          ) : !hasGuestToken && !user ? (
            <button onClick={() => { navigate("/guest/consent"); setSidebarOpen(false); }}>
              <ShieldCheck size={18} /><span>Subukan ng Libre</span>
            </button>
          ) : (
            trialScanners.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                className={scanner === key ? "active" : ""}
                aria-current={scanner === key ? "page" : undefined}
                disabled={busy}
                onClick={() => {
                  if (onScannerChange) {
                    onScannerChange(key);
                  } else {
                    navigate(`/guest/scanner?scanner=${key}`);
                  }
                  setSidebarOpen(false);
                }}
              >
                <Icon size={18} /><span>{label}</span>
              </button>
            ))
          )}
          <p className="sidebar-section-label">Verif.AI</p>
          <button onClick={() => navigate("/")}><ArrowLeft size={18} /><span>Back to home</span></button>
        </nav>
        <div className="sidebar-account">
          <span className="sidebar-avatar"><UserRound size={17} /></span>
          <div>
            <strong>Guest trial</strong>
            <span>No account required</span>
            <Link
              to="/register"
              className="sidebar-account-register-link"
              style={{
                display: "inline-block",
                marginTop: "4px",
                fontSize: "12px",
                color: "#F4B400",
                textDecoration: "underline",
                fontWeight: 700,
              }}
            >
              (Gumawa ng Account rito)
            </Link>
          </div>
        </div>
      </aside>
      <div className="dashboard-workspace">
        <header className="dashboard-topbar trial-topbar">
          <div className="trial-topbar-left">
            <button className="dashboard-menu-button" type="button" aria-label="Open navigation" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Menu size={19} /></button>
            <span className="trial-topbar-title">{title}</span>
          </div>
          <div className="trial-topbar-actions">
            {!user && (
              <Link className="button secondary trial-account-link" to="/register">Gumawa ng account</Link>
            )}
          </div>
        </header>
        <main className="dashboard-main trial-main">{children}</main>
        <footer className="dashboard-footer"><span>© 2026 Verif.AI</span><span>Built for more careful sharing online.</span></footer>
      </div>
    </div>
  );
}
