import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import axios from "axios";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { getCurrentUser, loginUser, registerUser } from "@/services/auth";

type AuthMode = "signin" | "signup";

export function AuthPage() {
  const [mode, setMode] = useState<AuthMode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Sign in or create an account | VeriFai";

    const token = localStorage.getItem("verifai_token");
    if (token) {
      getCurrentUser()
        .then((currentUser) => {
          localStorage.setItem("verifai_user", JSON.stringify(currentUser));
          navigate("/dashboard", { replace: true });
        })
        .catch(() => {
          localStorage.removeItem("verifai_token");
          localStorage.removeItem("verifai_user");
        });
    }

    return () => {
      document.title = "VeriFai — Digital Content Authenticity Analysis";
    };
  }, [navigate]);

  const changeMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setMessage("");
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setSubmitting(true);
    setMessage("");

    try {
      if (mode === "signup") {
        await registerUser({
          name,
          email,
          password,
        });

        setMessage("Account created successfully.");
      } else {
        await loginUser({
          email,
          password,
        });

        setMessage("Signed in successfully.");
      }

      navigate("/dashboard", { replace: true });
    } catch (error) {
      if (axios.isAxiosError(error)) {
        setMessage(
          error.response?.data?.detail ??
            "Unable to connect to the server.",
        );
      } else {
        setMessage("Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="About VeriFai">
        <Link className="auth-brand" to="/" aria-label="Return to VeriFai home">
          <span className="brand-mark" aria-hidden="true"><i /><i /></span>
          <span>VeriFai</span>
        </Link>
        <motion.div
          className="auth-artwork"
          initial={reduceMotion ? false : { opacity: 0, scale: 1.04 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        >
          <img src="/images/auth-authenticity-scan.png" alt="A human profile transitioning into a red digital authenticity scan" />
          <span className="auth-scan-line" aria-hidden="true" />
        </motion.div>
      </section>

      <section className="auth-panel">
        <div className="auth-panel-inner">
          <Link className="auth-back" to="/"><ArrowLeft size={16} /> Back to home</Link>

          <motion.div
            initial={reduceMotion ? false : { opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="kicker">VERIFAI ACCOUNT</p>
            <div className="auth-mode" role="tablist" aria-label="Authentication options">
              <button type="button" role="tab" aria-selected={mode === "signin"} onClick={() => changeMode("signin")}>Sign in</button>
              <button type="button" role="tab" aria-selected={mode === "signup"} onClick={() => changeMode("signup")}>Create account</button>
            </div>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                className="auth-form-stage"
                key={mode}
                initial={reduceMotion ? false : { opacity: 0, x: mode === "signup" ? 24 : -24 }}
                animate={{ opacity: 1, x: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0, x: mode === "signup" ? -16 : 16 }}
                transition={{ duration: 0.24, ease: "easeOut" }}
              >
                <h2>{mode === "signin" ? "Welcome back." : "Create your account."}</h2>
                <p className="auth-intro">
                  {mode === "signin"
                    ? "Enter your details to continue to your analysis workspace."
                    : "Set up your account to start using VeriFai on the web."}
                </p>

                <form className="auth-form" onSubmit={handleSubmit}>
                  {mode === "signup" && (
                    <div className="auth-field">
                      <label htmlFor="name">Full name</label>
                      <input
                        id="name"
                        name="name"
                        type="text"
                        autoComplete="name"
                        placeholder="Your full name"
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        required
                      />
                    </div>
                  )}
                  <div className="auth-field">
                    <label htmlFor="email">Email address</label>
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      required
                    />
                  </div>
                  <div className="auth-field">
                    <div className="auth-label-row">
                      <label htmlFor="password">Password</label>
                      {mode === "signin" && (
                        <button type="button" onClick={() => setMessage("Password recovery will be available when authentication is connected.")}>Forgot password?</button>
                      )}
                    </div>
                    <div className="password-input">
                      <input
                        id="password"
                        name="password"
                        type={showPassword ? "text" : "password"}
                        autoComplete={mode === "signin" ? "current-password" : "new-password"}
                        placeholder={mode === "signin" ? "Enter your password" : "At least 8 characters"}
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        minLength={8}
                        required
                      />
                      <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>
                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>
                  </div>

                  {mode === "signup" && (
                    <label className="auth-consent">
                      <input type="checkbox" required />
                      <span>I agree to VeriFai’s terms and acknowledge the privacy notice.</span>
                    </label>
                  )}

                  <button className="button primary large auth-submit" type="submit" disabled={submitting}>
                    {submitting ? "Checking details…" : mode === "signin" ? "Sign in" : "Create account"}
                    {!submitting && <ArrowRight size={17} />}
                  </button>
                  {message && <p className="auth-message" role="status"><LockKeyhole size={16} /> {message}</p>}
                </form>

                <p className="auth-switch">
                  {mode === "signin" ? "New to VeriFai?" : "Already have an account?"}
                  <button type="button" onClick={() => changeMode(mode === "signin" ? "signup" : "signin")}>
                    {mode === "signin" ? "Create an account" : "Sign in"}
                  </button>
                </p>
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </div>
      </section>
    </main>
  );
}
