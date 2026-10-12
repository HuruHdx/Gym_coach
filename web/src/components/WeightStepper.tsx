import { useEffect, useState } from "react";
import { WeightPickerModal } from "./WeightPickerModal";

type Props = {
  value: number | null | undefined;
  onChange: (val: number | null) => void;
  disabled?: boolean;
  step?: number;
  label?: string;
  className?: string;
};

function normalize(v: number | null | undefined): number | null {
  if (v == null || Number.isNaN(Number(v))) return null;
  const n = Number(v);
  return n <= 0 ? null : Math.round(n * 10) / 10;
}

export function WeightStepper({
  value,
  onChange,
  disabled = false,
  step = 2.5,
  label = "选择重量",
  className = "",
}: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  // 本地乐观状态：点 +/- 立刻变，不等父组件/接口回写
  const [local, setLocal] = useState<number | null>(() => normalize(value));

  useEffect(() => {
    setLocal(normalize(value));
  }, [value]);

  function adjust(delta: number) {
    if (disabled) return;
    let next: number | null;
    if (local == null) {
      // 自重时：减无效，加从 step 起
      if (delta < 0) return;
      next = Math.round(Math.max(step, delta) * 10) / 10;
    } else {
      const n = Math.max(0, Math.round((local + delta) * 10) / 10);
      next = n === 0 ? null : n;
    }
    setLocal(next);
    onChange(next);
  }

  const displayText = local == null ? "自重" : `${local}`;

  return (
    <>
      <div
        className={`inline-flex items-center rounded-lg border border-line bg-elevated p-0.5 shadow-sm ${className}`}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          disabled={disabled}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            adjust(-step);
          }}
          className="pressable grid h-9 w-9 place-items-center rounded-md text-base font-black text-ink hover:bg-bg disabled:opacity-30"
          aria-label={`减少 ${step}kg`}
        >
          −
        </button>

        <button
          type="button"
          disabled={disabled}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setModalOpen(true);
          }}
          className="pressable min-w-[64px] px-1.5 py-1 text-center text-sm font-semibold text-ink disabled:opacity-50"
          title="点击打开滑动选重"
        >
          <span className="font-num">{displayText}</span>
          {local != null && (
            <span className="ml-0.5 text-[10px] font-medium text-muted">kg</span>
          )}
        </button>

        <button
          type="button"
          disabled={disabled}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            adjust(step);
          }}
          className="pressable grid h-9 w-9 place-items-center rounded-md text-base font-black text-ink hover:bg-bg disabled:opacity-30"
          aria-label={`增加 ${step}kg`}
        >
          +
        </button>
      </div>

      <WeightPickerModal
        isOpen={modalOpen}
        value={local}
        title={label}
        onClose={() => setModalOpen(false)}
        onConfirm={(val) => {
          const next = normalize(val);
          setLocal(next);
          onChange(next);
        }}
      />
    </>
  );
}
