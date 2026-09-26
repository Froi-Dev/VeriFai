import { T } from "@/i18n/LanguageContext";
import { useLanguage } from "@/i18n/useLanguage";
import { LanguageToggle } from "@/components/LanguageToggle";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import axios from "axios";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowLeft, Check, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { Brand } from "@/components/Brand";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  getCurrentUser,
  isPasswordDistinct,
  isStrongPassword,
  loginUser,
  passwordRequirements,
  registerUser,
  requestPasswordReset,
  resetPassword,
} from "@/services/auth";

type AuthMode = "signin" | "signup" | "forgot" | "reset";

function errorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return "Hindi makumpleto ang kahilingang ito. Subukang muli.";
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : item?.message))
      .filter(Boolean)
      .join(". ");
  }
  return "Hindi makakonekta sa Verif.AI. Suriin ang koneksyon at subukang muli.";
}

export function AuthPage() {
  const { t } = useLanguage();
  const publicPreview = import.meta.env.VITE_LANDING_ONLY === "true";
  const location = useLocation();
  const resetToken = new URLSearchParams(location.search).get("token") ?? "";
  const [mode, setMode] = useState<AuthMode>(resetToken ? "reset" : location.pathname === "/register" ? "signup" : "signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();

  useEffect(() => {
    if (!publicPreview && !resetToken) {
      getCurrentUser()
        .then(() => navigate("/dashboard", { replace: true }))
        .catch(() => sessionStorage.removeItem("verifai_user"));
    }
    return () => {
      document.title = "Verif.AI — Digital Content Authenticity Analysis";
    };
  }, [mode, navigate, publicPreview, resetToken]);

  useEffect(() => {
    document.title = mode === "signup" ? t("Mag-register | Verif.AI") : mode === "signin" ? t("Mag-log in | Verif.AI") : `${t("I-reset ang password")} | Verif.AI`;
  }, [mode, t]);

  const changeMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setPassword("");
    setPasswordConfirmation("");
    setMessage("");
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (publicPreview) {
      setMessage("Authentication is unavailable in this public preview.");
      return;
    }
    if (
      (mode === "signup" || mode === "reset") &&
      !isStrongPassword(password, mode === "signup" ? email : "", mode === "signup" ? name : "")
    ) {
      setMessage("Paki-kumpleto ang bawat rekisito para sa ligtas na password.");
      return;
    }
    if ((mode === "signup" || mode === "reset") && password !== passwordConfirmation) {
      setMessage("Hindi tugma ang dalawang password.");
      return;
    }

    setSubmitting(true);
    setMessage("");
    try {
      if (mode === "signup") {
        await registerUser({ name, email, password });
        navigate("/dashboard", { replace: true });
      } else if (mode === "signin") {
        await loginUser({ email, password });
        navigate("/dashboard", { replace: true });
      } else if (mode === "forgot") {
        const result = await requestPasswordReset(email);
        setMessage(result.message);
      } else {
        if (!resetToken) throw new Error("Missing reset token");
        const result = await resetPassword(resetToken, password);
        setMessage(result.message);
        window.history.replaceState({}, "", `${import.meta.env.BASE_URL}auth`);
        setMode("signin");
        setPassword("");
        setPasswordConfirmation("");
      }
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const title = {
    signin: t("Mag-log in"),
    signup: t("Mag-register"),
    forgot: t("I-reset ang password"),
    reset: t("Pumili ng bagong password"),
  }[mode];

  const intro = {
    signin: t("I-access ang iyong Verif.AI workspace para sa walang limitasyong pagsusuri."),
    signup: t("Gumawa ng account para sa walang limitasyong access sa Verif.AI."),
    forgot: t("Ilagay ang iyong email address upang makatanggap ng time-limited reset link."),
    reset: t("Ang iyong bagong password ay magsa-sign out sa iyo sa lahat ng iba pang device."),
  }[mode];

  const needsPassword = mode === "signin" || mode === "signup" || mode === "reset";
  const needsConfirmation = mode === "signup" || mode === "reset";

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="About Verif.AI">
        <Brand className="auth-brand" />
        <div className="auth-story-copy">
          <p className="auth-tagline"><T>{"Tuklasin ang totoo sa bawat nilalaman."}</T></p>
        </div>
        <span className="auth-story-scan" aria-hidden="true" />
      </section>

      <section className="auth-panel">
        <div className="auth-panel-inner">
          <div className="auth-language"><LanguageToggle /></div>
          <Link className="auth-back" to="/"><ArrowLeft size={16} /><T>{" Bumalik sa home"}</T></Link>
          <motion.div initial={reduceMotion ? false : { opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
            {(mode === "signin" || mode === "signup") && (
              <div className="auth-mode" role="tablist" aria-label="Authentication options">
                <button type="button" role="tab" aria-selected={mode === "signin"} onClick={() => changeMode("signin")}><T>{"Mag-log in"}</T></button>
                <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => changeMode("signup")}><T>{"Mag-register"}</T></button>
              </div>
            )}
            <AnimatePresence mode="wait" initial={false}>
              <motion.div className="auth-form-stage" key={mode} initial={reduceMotion ? false : { opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={reduceMotion ? undefined : { opacity: 0, x: -16 }} transition={{ duration: 0.24, ease: "easeOut" }}>
                <h2>{title}</h2>
                <p className="auth-intro">{intro}</p>

                <form className="auth-form" onSubmit={handleSubmit}>
                  {mode === "signup" && (
                    <div className="auth-field">
                      <label htmlFor="name"><T>{"Buong pangalan"}</T></label>
                      <input id="name" name="name" type="text" autoComplete="name" placeholder={t("Pangalan at Apelyido")} value={name} onChange={(event) => setName(event.target.value)} maxLength={50} required />
                    </div>
                  )}
                  {mode !== "reset" && (
                    <div className="auth-field">
                      <label htmlFor="email">Email address</label>
                      <input id="email" name="email" type="email" autoComplete="email" placeholder={t("ikaw@halimbawa.com")} value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required />
                    </div>
                  )}
                  {needsPassword && (
                    <div className="auth-field">
                      <div className="auth-label-row">
                        <label htmlFor="password">{mode === "reset" ? t("Bagong password") : "Password"}</label>
                        {mode === "signin" && <button type="button" onClick={() => changeMode("forgot")}><T>{"Nakalimutan ang password?"}</T></button>}
                      </div>
                      <div className="password-input">
                        <input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete={mode === "signin" ? "current-password" : "new-password"} placeholder={mode === "signin" ? t("Ilagay ang iyong password") : t("Gumawa ng matatag na password")} value={password} onChange={(event) => setPassword(event.target.value)} minLength={mode === "signin" ? 1 : 12} maxLength={128} required />
                        <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? t("Itago ang password") : t("Ipakita ang password")}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button>
                      </div>
                      {needsConfirmation && (
                        <ul className="password-requirements" aria-label="Password requirements">
                          {passwordRequirements.map((requirement) => {
                            const met = requirement.test(password);
                            return <li key={requirement.label} data-met={met}><Check size={13} aria-hidden="true" /> {requirement.label}</li>;
                          })}
                          <li data-met={isPasswordDistinct(password, mode === "signup" ? email : "", mode === "signup" ? name : "")}><Check size={13} aria-hidden="true" /> Not common or personal</li>
                        </ul>
                      )}
                    </div>
                  )}
                  {needsConfirmation && (
                    <div className="auth-field">
                      <label htmlFor="password-confirmation"><T>{"Kumpirmahin ang password"}</T></label>
                      <input id="password-confirmation" name="password-confirmation" type={showPassword ? "text" : "password"} autoComplete="new-password" value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} minLength={12} maxLength={128} required />
                    </div>
                  )}
                  {mode === "signup" && (
                    <label className="auth-consent">
                      <input type="checkbox" required />
                      <span><T>{"Sumasang-ayon ako sa mga tuntunin ng Verif.AI at patakaran sa privacy."}</T></span>
                    </label>
                  )}

                  <button className="button primary large auth-submit" type="submit" disabled={submitting}>
                    {submitting ? t("Mangyaring maghintay…") : mode === "signin" ? t("Mag-log in") : mode === "signup" ? t("Mag-register") : mode === "forgot" ? t("Ipadala ang reset link") : t("Itakda ang bagong password")}
                  </button>
                  {message && <p className="auth-message" role="status" aria-live="polite"><LockKeyhole size={16} /> {t(message)}</p>}
                </form>

                <p className="auth-switch">
                  {mode === "signin" ? (
                    <><T>{"Bago palang sa Verif.AI?"}</T>{" "}
                      <button type="button" onClick={() => changeMode("signup")}><T>{"Gumawa ng account"}</T></button>
                    </>
                  ) : mode === "signup" ? (
                    <><T>{"May account na?"}</T>{" "}
                      <button type="button" onClick={() => changeMode("signin")}><T>{"Mag-log in"}</T></button>
                    </>
                  ) : (
                    <><T>{"Naalala mo na ang iyong password?"}</T>{" "}
                      <button type="button" onClick={() => changeMode("signin")}><T>{"Mag-log in"}</T></button>
                    </>
                  )}
                </p>

                {(mode === "signin" || mode === "signup") && (
                  <p style={{ textAlign: "center", marginTop: "14px" }}>
                    <Link
                      to="/guest/consent"
                      style={{
                        fontSize: "14px",
                        color: "var(--ph-blue)",
                        textDecoration: "none",
                        fontWeight: 600,
                      }}
                    ><T>{"(Gusto munang subukan? Pindutin rito)"}</T></Link>
                  </p>
                )}
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </div>
      </section>
    </main>
  );
}
