import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";

const ITEM_H = 40;
const VISIBLE = 5;
const PAD = ((VISIBLE - 1) / 2) * ITEM_H;

type Props = {
  open: boolean;
  title: string;
  values: number[];
  value: number | null;
  unit?: string;
  /** 允许选「不填」，值为 null */
  allowEmpty?: boolean;
  emptyLabel?: string;
  format?: (v: number) => string;
  onClose: () => void;
  onConfirm: (next: number | null) => void;
};

type WheelItem = { key: string; value: number | null; label: string };

/**
 * 手机滚轮选择：底部 sheet + scroll-snap。
 * 高亮条在文字下层，避免挡住选中项。
 */
export function WheelPickerSheet({
  open,
  title,
  values,
  value,
  unit,
  allowEmpty = false,
  emptyLabel = "不填",
  format = (v) => String(v),
  onClose,
  onConfirm,
}: Props) {
  const list = useMemo((): WheelItem[] => {
    const nums = values.map((v) => ({
      key: String(v),
      value: v as number | null,
      label: unit ? `${format(v)}${unit}` : format(v),
    }));
    if (!allowEmpty) return nums;
    return [{ key: "empty", value: null, label: emptyLabel }, ...nums];
  }, [allowEmpty, emptyLabel, format, unit, values]);

  const scrollerRef = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  const [draft, setDraft] = useState<number | null>(value);
  const settleTimer = useRef<number | null>(null);

  useEffect(() => {
    if (!open) {
      setShown(false);
      return;
    }
    // 未填时滚到列表中间作起点，但只有点「确定」才写入；不预填业务默认值
    const startIdx = (() => {
      const hit = list.findIndex((item) => item.value === value);
      if (hit >= 0) return hit;
      return Math.floor(list.length / 2);
    })();
    setDraft(list[startIdx]?.value ?? value);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const showId = window.requestAnimationFrame(() => setShown(true));
    const scrollId = window.requestAnimationFrame(() => {
      const el = scrollerRef.current;
      if (!el) return;
      el.scrollTop = startIdx * ITEM_H;
    });
    return () => {
      document.body.style.overflow = prev;
      window.cancelAnimationFrame(showId);
      window.cancelAnimationFrame(scrollId);
      if (settleTimer.current !== null) window.clearTimeout(settleTimer.current);
    };
  }, [open, value, list]);

  if (!open) return null;

  function indexFromScroll(top: number) {
    return Math.min(list.length - 1, Math.max(0, Math.round(top / ITEM_H)));
  }

  function onScroll() {
    const el = scrollerRef.current;
    if (!el) return;
    const idx = indexFromScroll(el.scrollTop);
    setDraft(list[idx]?.value ?? null);
    if (settleTimer.current !== null) window.clearTimeout(settleTimer.current);
    settleTimer.current = window.setTimeout(() => {
      const snapped = indexFromScroll(el.scrollTop);
      el.scrollTo({ top: snapped * ITEM_H, behavior: "smooth" });
      setDraft(list[snapped]?.value ?? null);
    }, 80);
  }

  const display =
    draft === null
      ? emptyLabel
      : unit
        ? `${format(draft)}${unit}`
        : format(draft);

  return createPortal(
    <SheetChrome title={title} shown={shown} onClose={onClose} confirmLabel={`确定（${display}）`} onConfirm={() => onConfirm(draft)}>
      <div className="relative mx-page overflow-hidden rounded-[var(--r-md)] border border-[var(--line)] bg-[var(--bg)]">
        <WheelHighlight />
        <WheelColumn
          scrollerRef={scrollerRef}
          list={list}
          draft={draft}
          onScroll={onScroll}
          onPick={(item, idx) => {
            setDraft(item.value);
            scrollerRef.current?.scrollTo({ top: idx * ITEM_H, behavior: "smooth" });
          }}
        />
      </div>
    </SheetChrome>,
    document.body,
  );
}

type DateProps = {
  open: boolean;
  title?: string;
  /** YYYY-MM-DD；null 表示未填 */
  value: string | null;
  onClose: () => void;
  onConfirm: (next: string | null) => void;
};

/** 年月日三列滚轮，主要给年龄 / 热量用。 */
export function DateWheelPickerSheet({
  open,
  title = "选择出生日期",
  value,
  onClose,
  onConfirm,
}: DateProps) {
  const years = useMemo(() => numberRange(2012, 1950, -1), []);
  const months = useMemo(() => numberRange(1, 12, 1), []);

  const parsed = parseIsoDate(value) ?? { y: 1995, m: 6, d: 15 };
  const [shown, setShown] = useState(false);
  const [y, setY] = useState(parsed.y);
  const [m, setM] = useState(parsed.m);
  const [d, setD] = useState(parsed.d);
  const [empty, setEmpty] = useState(value == null);

  const days = useMemo(() => numberRange(1, daysInMonth(y, m), 1), [y, m]);

  const yRef = useRef<HTMLDivElement>(null);
  const mRef = useRef<HTMLDivElement>(null);
  const dRef = useRef<HTMLDivElement>(null);
  const settle = useRef<number | null>(null);

  useEffect(() => {
    if (!open) {
      setShown(false);
      return;
    }
    const next = parseIsoDate(value) ?? { y: 1995, m: 6, d: 15 };
    setY(next.y);
    setM(next.m);
    setD(Math.min(next.d, daysInMonth(next.y, next.m)));
    setEmpty(value == null);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const showId = window.requestAnimationFrame(() => setShown(true));
    const scrollId = window.requestAnimationFrame(() => {
      scrollToValue(yRef.current, years, next.y);
      scrollToValue(mRef.current, months, next.m);
      scrollToValue(dRef.current, numberRange(1, daysInMonth(next.y, next.m), 1), next.d);
    });
    return () => {
      document.body.style.overflow = prev;
      window.cancelAnimationFrame(showId);
      window.cancelAnimationFrame(scrollId);
      if (settle.current !== null) window.clearTimeout(settle.current);
    };
  }, [open, value, years, months]);

  useEffect(() => {
    const max = daysInMonth(y, m);
    if (d > max) setD(max);
  }, [y, m, d]);

  if (!open) return null;

  function bindColumn(
    ref: RefObject<HTMLDivElement | null>,
    values: number[],
    set: (n: number) => void,
  ) {
    return () => {
      const el = ref.current;
      if (!el) return;
      const idx = Math.min(values.length - 1, Math.max(0, Math.round(el.scrollTop / ITEM_H)));
      set(values[idx] ?? values[0]!);
      setEmpty(false);
      if (settle.current !== null) window.clearTimeout(settle.current);
      settle.current = window.setTimeout(() => {
        const snapped = Math.min(values.length - 1, Math.max(0, Math.round(el.scrollTop / ITEM_H)));
        el.scrollTo({ top: snapped * ITEM_H, behavior: "smooth" });
        set(values[snapped] ?? values[0]!);
      }, 80);
    };
  }

  const iso = empty ? null : toIsoDate(y, m, Math.min(d, daysInMonth(y, m)));
  const confirmLabel = empty ? "确定（不填）" : `确定（${formatIsoDate(iso!)}）`;

  return createPortal(
    <SheetChrome
      title={title}
      shown={shown}
      onClose={onClose}
      confirmLabel={confirmLabel}
      onConfirm={() => onConfirm(iso)}
    >
      <div className="mx-page mb-2 flex justify-end">
        <button
          type="button"
          className={`pressable rounded-[var(--r-sm)] px-2.5 py-1 text-[var(--fs-label)] font-semibold ${
            empty
              ? "bg-[var(--accent)] text-[var(--accent-ink)]"
              : "border border-[var(--line)] text-[var(--text-2)]"
          }`}
          onClick={() => setEmpty(true)}
        >
          不填
        </button>
      </div>
      <div
        className={`relative mx-page overflow-hidden rounded-[var(--r-md)] border border-[var(--line)] bg-[var(--bg)] transition-opacity duration-state ${
          empty ? "opacity-40" : "opacity-100"
        }`}
      >
        <WheelHighlight />
        <div className="relative z-[1] grid grid-cols-3">
          <MiniWheel
            scrollerRef={yRef}
            values={years}
            value={y}
            suffix="年"
            onScroll={bindColumn(yRef, years, setY)}
            onPick={(v, idx) => {
              setY(v);
              setEmpty(false);
              yRef.current?.scrollTo({ top: idx * ITEM_H, behavior: "smooth" });
            }}
          />
          <MiniWheel
            scrollerRef={mRef}
            values={months}
            value={m}
            suffix="月"
            onScroll={bindColumn(mRef, months, setM)}
            onPick={(v, idx) => {
              setM(v);
              setEmpty(false);
              mRef.current?.scrollTo({ top: idx * ITEM_H, behavior: "smooth" });
            }}
          />
          <MiniWheel
            scrollerRef={dRef}
            values={days}
            value={Math.min(d, daysInMonth(y, m))}
            suffix="日"
            onScroll={bindColumn(dRef, days, setD)}
            onPick={(v, idx) => {
              setD(v);
              setEmpty(false);
              dRef.current?.scrollTo({ top: idx * ITEM_H, behavior: "smooth" });
            }}
          />
        </div>
      </div>
    </SheetChrome>,
    document.body,
  );
}

function SheetChrome({
  title,
  shown,
  onClose,
  confirmLabel,
  onConfirm,
  children,
}: {
  title: string;
  shown: boolean;
  onClose: () => void;
  confirmLabel: string;
  onConfirm: () => void;
  children: React.ReactNode;
}) {
  return (
    <>
      <div
        className={`mask${shown ? " show" : ""}`}
        role="presentation"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`sheet mx-auto w-full max-w-md${shown ? " show" : ""}`}
      >
        <div className="grab" aria-hidden />
        <div className="flex items-center justify-between px-page pb-2 pt-3">
          <h3 className="text-[var(--fs-title)] font-semibold text-[var(--text-1)]">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="pressable text-[var(--fs-label)] font-semibold text-[var(--text-2)]"
          >
            取消
          </button>
        </div>
        {children}
        <div className="px-page pb-3 pt-4">
          <button
            type="button"
            className="btn primary pressable block"
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </>
  );
}

/** 高亮在文字下层，只当选中带，不挡字 */
function WheelHighlight() {
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-1/2 z-0 h-10 -translate-y-1/2 border-y border-[var(--line)] bg-[var(--tint)]" />
      <div
        className="pointer-events-none absolute inset-x-0 top-0 z-[2] h-10"
        style={{ background: "linear-gradient(to bottom, var(--bg), transparent)" }}
      />
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 z-[2] h-10"
        style={{ background: "linear-gradient(to top, var(--bg), transparent)" }}
      />
    </>
  );
}

function WheelColumn({
  scrollerRef,
  list,
  draft,
  onScroll,
  onPick,
}: {
  scrollerRef: RefObject<HTMLDivElement | null>;
  list: WheelItem[];
  draft: number | null;
  onScroll: () => void;
  onPick: (item: WheelItem, idx: number) => void;
}) {
  return (
    <div
      ref={scrollerRef as RefObject<HTMLDivElement>}
      onScroll={onScroll}
      className="relative z-[1] h-[200px] overflow-y-auto overscroll-contain bg-transparent"
      style={{
        scrollSnapType: "y mandatory",
        paddingBlock: PAD,
        WebkitOverflowScrolling: "touch",
      }}
    >
      {list.map((item, idx) => {
        const active = item.value === draft;
        return (
          <button
            type="button"
            key={item.key}
            className={`flex h-10 w-full snap-center items-center justify-center bg-transparent transition-opacity duration-state ${
              active ? "opacity-100" : "opacity-40"
            }`}
            style={{ scrollSnapAlign: "center" }}
            onClick={() => onPick(item, idx)}
          >
            <span
              className={`num text-[var(--fs-body)] font-semibold ${
                active ? "text-[var(--text-1)]" : "text-[var(--text-2)]"
              }`}
            >
              {item.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function MiniWheel({
  scrollerRef,
  values,
  value,
  suffix,
  onScroll,
  onPick,
}: {
  scrollerRef: RefObject<HTMLDivElement | null>;
  values: number[];
  value: number;
  suffix: string;
  onScroll: () => void;
  onPick: (v: number, idx: number) => void;
}) {
  return (
    <div
      ref={scrollerRef as RefObject<HTMLDivElement>}
      onScroll={onScroll}
      className="h-[200px] overflow-y-auto overscroll-contain bg-transparent"
      style={{
        scrollSnapType: "y mandatory",
        paddingBlock: PAD,
        WebkitOverflowScrolling: "touch",
      }}
    >
      {values.map((v, idx) => {
        const active = v === value;
        return (
          <button
            type="button"
            key={v}
            className={`flex h-10 w-full snap-center items-center justify-center bg-transparent transition-opacity duration-state ${
              active ? "opacity-100" : "opacity-40"
            }`}
            style={{ scrollSnapAlign: "center" }}
            onClick={() => onPick(v, idx)}
          >
            <span
              className={`num text-[var(--fs-body)] font-semibold ${
                active ? "text-[var(--text-1)]" : "text-[var(--text-2)]"
              }`}
            >
              {v}
              <small className="ml-0.5 text-[var(--fs-micro)] font-medium text-[var(--text-3)]">
                {suffix}
              </small>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function scrollToValue(el: HTMLDivElement | null, values: number[], value: number) {
  if (!el) return;
  const idx = Math.max(0, values.indexOf(value));
  el.scrollTop = idx * ITEM_H;
}

export function numberRange(min: number, max: number, step = 1): number[] {
  if (step === 0) return [];
  const out: number[] = [];
  const scale = Math.abs(step) < 1 ? 10 : 1;
  if (step > 0) {
    for (let v = min; v <= max + 1e-9; v += step) {
      out.push(Math.round(v * scale) / scale);
    }
  } else {
    for (let v = min; v >= max - 1e-9; v += step) {
      out.push(Math.round(v * scale) / scale);
    }
  }
  return out;
}

export function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

export function toIsoDate(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function parseIsoDate(iso: string | null | undefined): { y: number; m: number; d: number } | null {
  if (!iso) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  const y = Number(match[1]);
  const m = Number(match[2]);
  const d = Number(match[3]);
  if (!Number.isFinite(y) || m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m)) return null;
  return { y, m, d };
}

export function formatIsoDate(iso: string): string {
  const p = parseIsoDate(iso);
  if (!p) return iso;
  return `${p.y}年${p.m}月${p.d}日`;
}
