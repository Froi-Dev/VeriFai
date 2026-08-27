import { api } from "@/lib/api";

export type UserRole = "user" | "moderator" | "admin";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
}

export interface AuthResponse {
  user: AuthUser;
}

export const passwordRequirements = [
  { label: "At least 12 characters", test: (value: string) => value.length >= 12 },
  { label: "One uppercase letter", test: (value: string) => /[A-Z]/.test(value) },
  { label: "One lowercase letter", test: (value: string) => /[a-z]/.test(value) },
  { label: "One number", test: (value: string) => /\d/.test(value) },
  { label: "One symbol", test: (value: string) => /[^A-Za-z0-9\s]/.test(value) },
] as const;

const commonPasswords = new Set([
  "123456789012",
  "adminpassword",
  "letmeinplease",
  "password123!",
  "qwertyuiop123!",
  "welcome123!",
]);

export function isPasswordDistinct(value: string, email = "", name = "") {
  const folded = value.normalize("NFKC").toLocaleLowerCase();
  const emailName = email.split("@", 1)[0].trim().toLocaleLowerCase();
  const compactName = name.replace(/[^\p{L}\p{N}_]/gu, "").toLocaleLowerCase();
  const compactPassword = folded.replace(/[^\p{L}\p{N}_]/gu, "");
  return !commonPasswords.has(folded)
    && !(emailName.length >= 4 && folded.includes(emailName))
    && !(compactName.length >= 4 && compactPassword.includes(compactName));
}

export function isStrongPassword(value: string, email = "", name = "") {
  return passwordRequirements.every((requirement) => requirement.test(value))
    && isPasswordDistinct(value, email, name);
}

function rememberUser(user: AuthUser) {
  sessionStorage.setItem("verifai_user", JSON.stringify(user));
}

export async function registerUser(data: {
  name: string;
  email: string;
  password: string;
}) {
  const response = await api.post<AuthResponse>("/auth/register", data);
  rememberUser(response.data.user);
  return response.data;
}

export async function loginUser(data: { email: string; password: string }) {
  const response = await api.post<AuthResponse>("/auth/login", data);
  rememberUser(response.data.user);
  return response.data;
}

export async function refreshSession() {
  const response = await api.post<AuthResponse>("/auth/refresh");
  rememberUser(response.data.user);
  return response.data;
}

export async function getCurrentUser() {
  const response = await api.get<AuthUser>("/auth/me");
  rememberUser(response.data);
  return response.data;
}

export async function requestPasswordReset(email: string) {
  const response = await api.post<{ message: string }>(
    "/auth/password-reset/request",
    { email },
    { headers: { "Idempotency-Key": crypto.randomUUID() } },
  );
  return response.data;
}

export async function resetPassword(token: string, password: string) {
  const response = await api.post<{ message: string }>(
    "/auth/password-reset/confirm",
    { token, password },
  );
  sessionStorage.removeItem("verifai_user");
  return response.data;
}

export async function logoutUser() {
  try {
    await api.post("/auth/logout");
  } finally {
    sessionStorage.removeItem("verifai_user");
  }
}
