import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type Props = {
  value: number | null | undefined;
  onChange: (val: number) => void;
  disabled?: boolean;
  defaultValue?: number;
  label?: string;
  className?: string;
};

const PRESETS = [6, 8, 10, 12, 15, 20];

function clampReps(n: number) {
  return Math.max(1, Math.min(30, Math.round(n)));
}

export function RepsStepper({
  value,
  onChange,
  disabled = false,
  defaultValue = 10,
  label = "选择次数",
  className = "",
}: Props) {
  const shown = value != null && Number.isFinite(Number(value)) ? clampReps(Number(value)) : defaultValue;
  const [local, setLocal] = useState(shown);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(shown);

  useEffect(() => {
    setLocal(shown);
  }, [shown]);

  useEffect(() => {
    if (!open) return;
    setDraft(local);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open, local]);

  function commit(next: number) {
    if (disabled) return;
    const n = clampReps(next);
    setLocal(n);
    onChange(n);
  }

  const modal =
    open &&
    createPortal(
      <div className="fixed inset-0 z-[200] flex items-end justify-center">
        <button type="button" className="absolute inset-0 bg-black/55" aria-label="关闭" onClick={() => setOpen(false)} />
        <div
          role="dialog"
          aria-modal="true"
          className="relative z-10 w-full max-w-md rounded-t-2xl border-t border-line bg-elevated px-5 pb-[max(20px,env(safe-area-inset-bottom))] pt-4 shadow-2xl"
        >
          <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-base font-semibold text-ink">{label}</h3>
            <button type="button" onClick={() => setOpen(false)} className="pressable text-sm font-semibold text-muted">
              ✕
            </button>
          </div>
          <div className="my-5 flex items-baseline justify-center gap-1.5">
            <span className="font-num text-5xl font-semibold text-ink">{draft}</span>
            <span className="text-base text-muted">次</span>
          </div>
          <div className="text-[11px] font-semibold text-muted">常用次数</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PRESETS.map((n) => (
              <button
                key={n}
                type="button"
                className={`pressable min-w-[42px] rounded-md px-2.5 py-1.5 text-xs font-semibold ${
                  draft === n ? "bg-accent text-accent-ink" : "border border-line bg-bg text-ink"
                }`}
                onClick={() => setDraft(n)}
              >
                {n}
              </button>
            ))}
          </div>
          <div className="my-4 rounded-xl border border-line bg-bg p-3">
            <div className="flex items-center justify-between text-xs text-muted">
              <span>滑动选择</span>
              <span className="font-num font-semibold text-ink">{draft} 次</span>
            </div>
            <input
              type="range"
              min={1}
              max={30}
              step={1}
              value={draft}
              onChange={(e) => setDraft(Number(e.target.value))}
              className="mt-2 h-2.5 w-full cursor-pointer appearance-none rounded-lg bg-line accent-accent"
            />
            <div className="mt-1 flex justify-between text-[10px] text-muted">
              <span>1</span>
              <span>10</span>
              <span>20</span>
              <span>30</span>
            </div>
          </div>
          <button
            type="button"
            className="pressable w-full rounded-lg bg-accent py-3.5 text-base font-bold text-accent-ink"
            onClick={() => {
              commit(draft);
              setOpen(false);
            }}
          >
            确定（{draft} 次）
          </button>
        </div>
      </div>,
      document.body,
    );

  return (
    <>
      <div
        className={`inline-flex items-center rounded-lg border border-line bg-elevated p-0.5 shadow-sm ${className}`}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          disabled={disabled || local <= 1}
          onClick={() => commit(local - 1)}
          className="pressable grid h-9 w-8 place-items-center rounded-md text-base font-black text-ink disabled:opacity-30"
          aria-label="减少1次"
        >
          −
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen(true)}
          className="pressable min-w-[52px] px-1 py-1 text-center text-sm font-semibold text-ink"
          title="点击选择次数"
        >
          <span className="font-num">{local}</span>
          <span className="ml-0.5 text-[10px] text-muted">次</span>
        </button>
        <button
          type="button"
          disabled={disabled || local >= 30}
          onClick={() => commit(local + 1)}
          className="pressable grid h-9 w-8 place-items-center rounded-md text-base font-black text-ink disabled:opacity-30"
          aria-label="增加1次"
        >
          +
        </button>
      </div>
      {modal}
    </>
  );
}
