import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

export function ExtensionPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const user = sessionStorage.getItem("verifai_user");
    if (user) {
      navigate("/dashboard/download-extension", { replace: true });
    } else {
      navigate("/register", { replace: true });
    }
  }, [navigate]);

  return null;
}
