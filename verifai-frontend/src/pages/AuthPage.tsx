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
  if (!axios.isAxiosError(error)) return "We couldn’t complete this request. Try again.";
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => typeof item === "string" ? item : item?.message)
      .filter(Boolean)
      .join(". ");
  }
  return "We couldn’t connect to Verif.Ai. Check your connection and try again.";
}

export function AuthPage() {
  const publicPreview = import.meta.env.VITE_LANDING_ONLY === "true";
  const location = useLocation();
  const resetToken = new URLSearchParams(location.search).get("token") ?? "";
  const [mode, setMode] = useState<AuthMode>(resetToken ? "reset" : "signin");
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
    document.title = "Sign in or create an account | Verif.Ai";
    if (!publicPreview && !resetToken) {
      getCurrentUser()
        .then(() => navigate("/dashboard", { replace: true }))
        .catch(() => sessionStorage.removeItem("verifai_user"));
    }
    return () => {
      document.title = "Verif.Ai — Digital Content Authenticity Analysis";
    };
  }, [navigate, publicPreview, resetToken]);

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
      (mode === "signup" || mode === "reset")
      && !isStrongPassword(password, mode === "signup" ? email : "", mode === "signup" ? name : "")
    ) {
      setMessage("Please meet every password requirement.");
      return;
    }
    if ((mode === "signup" || mode === "reset") && password !== passwordConfirmation) {
      setMessage("Passwords do not match.");
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
    signin: "Welcome back.",
    signup: "Create your account.",
    forgot: "Reset your password.",
    reset: "Choose a new password.",
  }[mode];
  const intro = {
    signin: "Pick up where you left off. Sign in to check content and review your history.",
    signup: "Set up your account to start using Verif.Ai on the web.",
    forgot: "Enter your email. If an account exists, we’ll send a time-limited reset link.",
    reset: "Your new password will sign you out on every other device.",
  }[mode];
  const needsPassword = mode === "signin" || mode === "signup" || mode === "reset";
  const needsConfirmation = mode === "signup" || mode === "reset";

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="About Verif.Ai">
        <Brand className="auth-brand" />
        <div className="auth-story-copy">
          <p className="auth-tagline">Tuklasin ang totoo sa bawat nilalaman.</p>
        </div>
        <span className="auth-story-scan" aria-hidden="true" />
      </section>

      <section className="auth-panel">
        <div className="auth-panel-inner">
          <Link className="auth-back" to="/"><ArrowLeft size={16} /> Back to home</Link>
          <motion.div initial={reduceMotion ? false : { opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
            {(mode === "signin" || mode === "signup") && (
              <div className="auth-mode" role="tablist" aria-label="Authentication options">
                <button type="button" role="tab" aria-selected={mode === "signin"} onClick={() => changeMode("signin")}>Sign in</button>
                <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => changeMode("signup")}>Create account</button>
              </div>
            )}
            <AnimatePresence mode="wait" initial={false}>
              <motion.div className="auth-form-stage" key={mode} initial={reduceMotion ? false : { opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={reduceMotion ? undefined : { opacity: 0, x: -16 }} transition={{ duration: 0.24, ease: "easeOut" }}>
                <h2>{title}</h2>
                <p className="auth-intro">{intro}</p>

                <form className="auth-form" onSubmit={handleSubmit}>
                  {mode === "signup" && (
                    <div className="auth-field">
                      <label htmlFor="name">Full name</label>
                      <input id="name" name="name" type="text" autoComplete="name" placeholder="Your full name" value={name} onChange={(event) => setName(event.target.value)} maxLength={50} required />
                    </div>
                  )}
                  {mode !== "reset" && (
                    <div className="auth-field">
                      <label htmlFor="email">Email address</label>
                      <input id="email" name="email" type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={254} required />
                    </div>
                  )}
                  {needsPassword && (
                    <div className="auth-field">
                      <div className="auth-label-row">
                        <label htmlFor="password">{mode === "reset" ? "New password" : "Password"}</label>
                        {mode === "signin" && <button type="button" onClick={() => changeMode("forgot")}>Forgot password?</button>}
                      </div>
                      <div className="password-input">
                        <input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete={mode === "signin" ? "current-password" : "new-password"} placeholder={mode === "signin" ? "Enter your password" : "Create a strong password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={mode === "signin" ? 1 : 12} maxLength={128} required />
                        <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button>
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
                      <label htmlFor="password-confirmation">Confirm password</label>
                      <input id="password-confirmation" name="password-confirmation" type={showPassword ? "text" : "password"} autoComplete="new-password" value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} minLength={12} maxLength={128} required />
                    </div>
                  )}
                  {mode === "signup" && (
                    <label className="auth-consent">
                      <input type="checkbox" required />
                      <span>I agree to Verif.Ai’s terms and acknowledge the privacy notice.</span>
                    </label>
                  )}

                  <button className="button primary large auth-submit" type="submit" disabled={submitting}>
                    {submitting ? "Please wait…" : mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : mode === "forgot" ? "Send reset link" : "Set new password"}
                  </button>
                  {message && <p className="auth-message" role="status" aria-live="polite"><LockKeyhole size={16} /> {message}</p>}
                </form>

                <p className="auth-switch">
                  {mode === "signin" ? "New to Verif.Ai?" : mode === "signup" ? "Already have an account?" : "Remembered your password?"}
                  <button type="button" onClick={() => changeMode(mode === "signin" ? "signup" : "signin")}>{mode === "signin" ? "Create an account" : "Sign in"}</button>
                </p>
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </div>
      </section>
    </main>
  );
}
