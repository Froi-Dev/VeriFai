import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthPage, DashboardPage, HomePage } from "@/pages";
import { getCurrentUser } from "@/services/auth";

function ProtectedDashboard() {
  const [sessionState, setSessionState] = useState<
    "checking" | "authenticated" | "anonymous"
  >("checking");

  useEffect(() => {
    const token = localStorage.getItem("verifai_token");

    if (!token) {
      setSessionState("anonymous");
      return;
    }

    getCurrentUser()
      .then((user) => {
        localStorage.setItem("verifai_user", JSON.stringify(user));
        setSessionState("authenticated");
      })
      .catch(() => {
        localStorage.removeItem("verifai_token");
        localStorage.removeItem("verifai_user");
        setSessionState("anonymous");
      });
  }, []);

  if (sessionState === "checking") {
    return (
      <main className="dashboard-auth-check" aria-live="polite">
        <LoaderCircle className="spin" size={22} />
        <span>Opening your workspace…</span>
      </main>
    );
  }

  if (sessionState === "anonymous") {
    return <Navigate to="/auth" replace />;
  }

  return <DashboardPage />;
}

export default function App() {
  const landingOnly = import.meta.env.VITE_LANDING_ONLY === "true";

  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        {!landingOnly && <Route path="/auth" element={<AuthPage />} />}
        {!landingOnly && <Route path="/dashboard/*" element={<ProtectedDashboard />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
