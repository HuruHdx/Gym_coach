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

type FeedbackSnapshot = {
  toasts: ToastItem[];
  loading: boolean;
  loadingText: string;
};

let snapshot: FeedbackSnapshot = {
  toasts,
  loading: false,
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
  async wrap<T>(text: string, work: () => Promise<T>): Promise<T> {
    loading.show(text);
    try {
      return await work();
    } finally {
      loading.hide();
    }
  },
};
