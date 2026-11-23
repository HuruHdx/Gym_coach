export type ToastKind = "ok" | "err" | "info";

export type ToastItem = {
  id: number;
  kind: ToastKind;
  text: string;
};

type Listener = () => void;

let toastSeq = 1;
let toasts: ToastItem[] = [];
let loadingCount = 0;
let loadingText = "处理中…";
const listeners = new Set<Listener>();

// 快照必须缓存同一个对象引用：useSyncExternalStore 用 Object.is 比较，
// 每次返回新对象会被判定为"永远在变"，导致 React 无限重渲染（首页白屏）。
let snapshot = {
  toasts,
  loading: loadingCount > 0,
  loadingText,
};

function emit() {
  snapshot = {
    toasts,
    loading: loadingCount > 0,
    loadingText,
  };
  listeners.forEach((fn) => fn());
}

export function subscribeFeedback(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getFeedbackSnapshot() {
  return snapshot;
}

function pushToast(kind: ToastKind, text: string, ms = 1600) {
  const msg = text.trim();
  if (!msg) return;
  const id = toastSeq++;
  toasts = [...toasts.filter((t) => t.text !== msg || t.kind !== kind), { id, kind, text: msg }];
  emit();
  window.setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id);
    emit();
  }, ms);
}

export const toast = {
  ok(text: string, ms?: number) {
    pushToast("ok", text, ms);
  },
  err(text: string, ms?: number) {
    pushToast("err", text, ms ?? 2200);
  },
  info(text: string, ms?: number) {
    pushToast("info", text, ms);
  },
  dismiss(id?: number) {
    toasts = id == null ? [] : toasts.filter((t) => t.id !== id);
    emit();
  },
};

export const loading = {
  show(text = "处理中…") {
    loadingCount += 1;
    loadingText = text;
    emit();
  },
  hide() {
    loadingCount = Math.max(0, loadingCount - 1);
    if (loadingCount === 0) loadingText = "处理中…";
    emit();
  },
  /** 遮罩手动关闭：清零计数，避免与仍在跑的 wrap 错位 */
  forceHide() {
    loadingCount = 0;
    loadingText = "处理中…";
    emit();
  },
  async wrap<T>(text: string, work: () => Promise<T>): Promise<T> {
    loading.show(text);
    try {
      return await work();
    } finally {
      loading.hide();
    }
  },
};

/** 把 api 抛出的 `401: …` / `500: …` 收成短句，给 toast 用 */
export function feedbackError(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  if (raw.startsWith("401")) return "登录已失效，请重新登录";
  if (raw.startsWith("403")) return "没有权限做这件事";
  const matched = raw.match(/^\d{3}:\s*([\s\S]*)$/);
  if (matched) {
    const body = matched[1].trim().replace(/\s+/g, " ");
    return (body || "请求失败").slice(0, 120);
  }
  return raw.trim().slice(0, 160) || "出了点问题";
}
