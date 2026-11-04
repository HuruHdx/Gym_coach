const TOKEN_KEY = "gym-app-token";
const AUTH_FLAG = "gym-authed";
/** 与 profileView 里本机性别/生日 key 对齐，登出时清掉避免串号 */
const PROFILE_EXTRAS_KEY = "gym-coach-profile-extras";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(AUTH_FLAG);
  localStorage.removeItem(PROFILE_EXTRAS_KEY);
}

export function markAuthed() {
  localStorage.setItem(AUTH_FLAG, "1");
}

export function isAuthed(): boolean {
  return localStorage.getItem(AUTH_FLAG) === "1" && Boolean(getToken());
}

/**
 * 业务请求：自动带 Authorization: Bearer <jwt>。
 * 401 清本地登录态，交给上层回登录页。
 */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    clearAuth();
    const text = await res.text();
    throw new Error(`401: ${text || "unauthorized"}`);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
