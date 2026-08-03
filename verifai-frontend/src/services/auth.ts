import { api } from "@/lib/api";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
}

export interface AuthResponse {
  token: string;
  token_type: "bearer";
  user: AuthUser;
}

export async function registerUser(data: {
  name: string;
  email: string;
  password: string;
}) {
  const response = await api.post<AuthResponse>("/auth/register", data);

  localStorage.setItem("verifai_token", response.data.token);
  localStorage.setItem("verifai_user", JSON.stringify(response.data.user));

  return response.data;
}

export async function loginUser(data: {
  email: string;
  password: string;
}) {
  const response = await api.post<AuthResponse>("/auth/login", data);

  localStorage.setItem("verifai_token", response.data.token);
  localStorage.setItem("verifai_user", JSON.stringify(response.data.user));

  return response.data;
}

export async function getCurrentUser() {
  const response = await api.get<AuthUser>("/auth/me");
  return response.data;
}

export async function logoutUser() {
  try {
    await api.post("/auth/logout");
  } finally {
    localStorage.removeItem("verifai_token");
    localStorage.removeItem("verifai_user");
  }
}
