import type {
  FollowingProgress,
  PlanDetail,
  PlanExpandResponse,
  PlanListResponse,
} from "../types";

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
  try {
    sessionStorage.removeItem("last_reply");
  } catch {
    /* ignore */
  }
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

export type PlanListQuery = {
  type?: "framework" | "fixed" | "";
  scene?: string;
  muscle?: string;
  level?: string;
};

export function fetchPlans(query: PlanListQuery = {}) {
  const params = new URLSearchParams();
  if (query.type) params.set("type", query.type);
  if (query.scene && query.scene !== "全部") params.set("scene", query.scene);
  if (query.muscle && query.muscle !== "全部") params.set("muscle", query.muscle);
  if (query.level && query.level !== "全部") params.set("level", query.level);
  const qs = params.toString();
  return api<PlanListResponse>(`/api/plans${qs ? `?${qs}` : ""}`);
}

export function fetchPlanDetail(id: string) {
  return api<PlanDetail>(`/api/plans/${encodeURIComponent(id)}`);
}

export function expandPlan(id: string, blockId: number) {
  return api<PlanExpandResponse>(`/api/plans/${encodeURIComponent(id)}/expand`, {
    method: "POST",
    body: JSON.stringify({ block_id: blockId }),
  });
}

export function fetchFollowing() {
  return api<FollowingProgress>("/api/plans/following");
}

export function followPlan(id: string) {
  return api<FollowingProgress>(`/api/plans/${encodeURIComponent(id)}/follow`, {
    method: "POST",
  });
}

export function unfollowPlan() {
  return api<FollowingProgress>("/api/plans/follow", { method: "DELETE" });
}
