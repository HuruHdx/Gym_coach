import { useSyncExternalStore } from "react";
import { getFeedbackSnapshot, loading, subscribeFeedback, toast } from "./store";
import { Spinner } from "./Spinner";

export function FeedbackHost() {
  const snap = useSyncExternalStore(subscribeFeedback, getFeedbackSnapshot, getFeedbackSnapshot);

  return (
    <>
      <div
        className="pointer-events-none fixed inset-x-0 bottom-[calc(88px+env(safe-area-inset-bottom))] z-[70] flex flex-col items-center gap-2 px-4"
        aria-live="polite"
        aria-relevant="additions"
      >
        {snap.toasts.map((t) => (
          <div
            key={t.id}
            className={[
              "pointer-events-auto flex max-w-[min(92vw,360px)] items-center gap-2 rounded-full px-3.5 py-2 text-micro font-semibold shadow-float rise-in",
              t.kind === "err"
                ? "bg-danger text-bg"
                : t.kind === "ok"
                  ? "bg-done text-accent-ink"
                  : "bg-ink text-accent-ink",
            ].join(" ")}
            role={t.kind === "err" ? "alert" : "status"}
          >
            <span>{t.text}</span>
            <button
              type="button"
              className="opacity-70"
              onClick={() => toast.dismiss(t.id)}
              aria-label="关闭"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {snap.loading ? (
        <div
          className="bg-scrim fixed inset-0 z-[70] grid place-items-center"
          role="status"
          aria-live="assertive"
          aria-busy="true"
        >
          <div className="relative flex min-w-[148px] items-center gap-2.5 rounded-xl border border-line bg-surface px-4 py-3.5 pr-9 text-sm text-ink shadow-float">
            <Spinner size={18} />
            <span>{snap.loadingText}</span>
            <button
              type="button"
              className="absolute right-2.5 top-2 text-meta text-muted"
              onClick={() => loading.forceHide()}
              aria-label="关闭遮罩"
            >
              ✕
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
