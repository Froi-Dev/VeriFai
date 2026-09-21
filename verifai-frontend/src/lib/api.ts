import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

interface RetryableRequest extends InternalAxiosRequestConfig {
  _sessionRetry?: boolean;
}

export const api = axios.create({
  // Prefer environment variable, fallback to live Render backend in production
  baseURL:
    import.meta.env.VITE_API_URL ||
    (import.meta.env.PROD
      ? "https://verifai-api-10as.onrender.com/api/v1"
      : "/api/v1"),
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
  timeout: 45_000,
});

let refreshInFlight: Promise<void> | null = null;

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const request = error.config as RetryableRequest | undefined;
    const isRefresh = request?.url?.endsWith("/auth/refresh");
    const neverRefresh = [
      "/auth/login",
      "/auth/register",
      "/auth/password-reset/request",
      "/auth/password-reset/confirm",
    ].some((path) => request?.url?.endsWith(path));
    const isGuest = request?.url?.startsWith("/guest/");
    const canRefresh = error.response?.status === 401 && request && !request._sessionRetry && !isRefresh && !neverRefresh && !isGuest;

    if (!canRefresh) {
      return Promise.reject(error);
    }

    request._sessionRetry = true;
    refreshInFlight ??= api.post("/auth/refresh").then(() => undefined).finally(() => {
      refreshInFlight = null;
    });

    try {
      await refreshInFlight;
      return api(request);
    } catch {
      sessionStorage.removeItem("verifai_user");
      return Promise.reject(error);
    }
  },
);
