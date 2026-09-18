import axios from "axios";
import { api } from "@/lib/api";

export type Scanner = "text" | "image" | "news";
export type Quota = { quotas: Record<Scanner, { limit: number; used: number; remaining: number }> };
export function guestHeaders() {
  const token = localStorage.getItem("verifai_guest");
  return token ? { "X-Guest-Token": token } : {};
}
export async function getQuota() {
  return (await api.get<Quota>("/guest/quota", { headers: guestHeaders() })).data;
}
export async function acceptConsent() {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (context) { context.font = "16px sans-serif"; context.fillText("VerifAI trial", 4, 20); }
  const bytes = new TextEncoder().encode(canvas.toDataURL() + navigator.userAgent);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  const fingerprint = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, "0")).join("");
  const { data } = await api.post("/guest/consent", {
    cookies: true,
    service_terms: true,
    essential: true,
    quota_tracking: true,
    device_terms: true,
    fingerprint,
  });
  localStorage.setItem("verifai_guest", data.guest_token);
}
export function guestError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (detail?.code === "QUOTA_EXCEEDED") return "Naubos na ang libreng pagsubok para sa scanner na ito.";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map(item => item.message || item.msg).join(". ");
  }
  return "Hindi makumpleto ang request. Pakisubukang muli.";
}
