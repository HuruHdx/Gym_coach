import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

type Props = {
  isOpen: boolean;
  value: number | null | undefined;
  title?: string;
  onClose: () => void;
  onConfirm: (val: number | null) => void;
};

const COMMON_PRESETS = [
  { label: "自重", value: null },
  { label: "5", value: 5 },
  { label: "10", value: 10 },
  { label: "15", value: 15 },
  { label: "20", value: 20 },
  { label: "25", value: 25 },
  { label: "30", value: 30 },
  { label: "35", value: 35 },
  { label: "40", value: 40 },
  { label: "50", value: 50 },
  { label: "60", value: 60 },
  { label: "70", value: 70 },
  { label: "80", value: 80 },
  { label: "100", value: 100 },
];

export function WeightPickerModal({
  isOpen,
  value,
  title = "选择重量",
  onClose,
  onConfirm,
}: Props) {
  const [current, setCurrent] = useState<number | null>(value ?? 20);

  useEffect(() => {
    if (isOpen) {
      setCurrent(value == null || value === 0 ? null : Number(value));
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [isOpen, value]);

  if (!isOpen) return null;

  function adjust(delta: number) {
    if (current === null) {
      if (delta < 0) return;
      setCurrent(Math.max(2.5, delta));
      return;
    }
    const next = Math.max(0, Math.min(250, Math.round((current + delta) * 10) / 10));
    setCurrent(next === 0 ? null : next);
  }

  const modal = (
    <div className="fixed inset-0 z-[200] flex items-end justify-center">
      <button
        type="button"
        className="absolute inset-0 bg-black/55"
        aria-label="关闭"
        onClick={onClose}
      />

      <div
        role="dialog"
        aria-modal="true"
        className="relative z-10 w-full max-w-md rounded-t-2xl border-t border-line bg-elevated px-5 pb-[max(20px,env(safe-area-inset-bottom))] pt-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />

        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold leading-snug text-ink">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="pressable shrink-0 rounded-md px-2 py-1 text-sm font-semibold text-muted hover:text-ink"
          >
            ✕
          </button>
        </div>

        {/* 大号数字：用易读的等宽数字，不用展示字体 */}
        <div className="my-5 flex items-baseline justify-center gap-1.5">
          {current === null ? (
            <span className="text-4xl font-semibold tracking-tight text-ink">自重</span>
          ) : (
            <>
              <span className="font-num text-5xl font-semibold tracking-tight text-ink">
                {current}
              </span>
              <span className="text-base font-medium text-muted">kg</span>
            </>
          )}
        </div>

        <div className="mb-4">
          <div className="text-[11px] font-semibold text-muted">常用预设</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {COMMON_PRESETS.map((p) => {
              const active = current === p.value;
              return (
                <button
                  key={p.label}
                  type="button"
                  className={`pressable min-w-[42px] rounded-md px-2.5 py-1.5 text-xs font-semibold transition-all ${
                    active
                      ? "bg-accent text-accent-ink"
                      : "border border-line bg-bg text-ink"
                  }`}
                  onClick={() => setCurrent(p.value)}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="my-4 rounded-xl border border-line bg-bg p-3">
          <div className="flex items-center justify-between text-xs text-muted">
            <span>滑动选择</span>
            <span className="font-num font-semibold text-ink">
              {current === null ? "自重" : `${current} kg`}
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="150"
            step="2.5"
            value={current === null ? 0 : current}
            onChange={(e) => {
              const val = Number(e.target.value);
              setCurrent(val === 0 ? null : val);
            }}
            className="mt-2 h-2.5 w-full cursor-pointer appearance-none rounded-lg bg-line accent-accent"
          />
          <div className="mt-1 flex justify-between text-[10px] font-medium text-muted">
            <span>自重</span>
            <span>25</span>
            <span>50</span>
            <span>75</span>
            <span>100</span>
            <span>150</span>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-2">
          {[
            { label: "−5", d: -5 },
            { label: "−2.5", d: -2.5 },
            { label: "+2.5", d: 2.5 },
            { label: "+5", d: 5 },
          ].map((b) => (
            <button
              key={b.label}
              type="button"
              className="pressable rounded-lg border border-line bg-bg py-2.5 text-sm font-semibold text-ink active:bg-line/40"
              onClick={() => adjust(b.d)}
            >
              {b.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => {
            onConfirm(current);
            onClose();
          }}
          className="pressable mt-4 w-full rounded-lg bg-accent py-3.5 text-base font-bold text-accent-ink"
        >
          确定选择（{current === null ? "自重" : `${current} kg`}）
        </button>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
