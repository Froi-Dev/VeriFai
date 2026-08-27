import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

interface RetryableRequest extends InternalAxiosRequestConfig {
  _sessionRetry?: boolean;
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
  timeout: 15_000,
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
    const canRefresh = error.response?.status === 401 && request && !request._sessionRetry && !isRefresh && !neverRefresh;

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
