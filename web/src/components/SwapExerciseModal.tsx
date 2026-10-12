import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../lib/api";
import type { AlternativesResponse } from "../types";

type Props = {
  isOpen: boolean;
  currentTitle: string;
  muscle: string;
  onClose: () => void;
  onSelect: (newTitle: string, category?: string) => void;
};

const CATEGORIES = ["全部", "器械", "自由重量", "绳索", "自重"];

export function SwapExerciseModal({
  isOpen,
  currentTitle,
  muscle,
  onClose,
  onSelect,
}: Props) {
  const [data, setData] = useState<AlternativesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeCategory, setActiveCategory] = useState("全部");
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setQuery("");
    setActiveCategory("全部");
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    api<AlternativesResponse>(
      `/api/training/alternatives?muscle=${encodeURIComponent(muscle)}&exclude=${encodeURIComponent(currentTitle)}`,
    )
      .then((res) => setData(res))
      .catch((err) => console.error("fetch alternatives err", err))
      .finally(() => setLoading(false));

    return () => {
      document.body.style.overflow = prev;
    };
  }, [isOpen, muscle, currentTitle]);

  const filteredItems = useMemo(() => {
    if (!data?.items) return [];
    return data.items.filter((item) => {
      const matchCat = activeCategory === "全部" || item.category === activeCategory;
      const q = query.trim().toLowerCase();
      const matchQuery =
        !q ||
        item.name.toLowerCase().includes(q) ||
        (item.tips && item.tips.toLowerCase().includes(q));
      return matchCat && matchQuery;
    });
  }, [data, activeCategory, query]);

  if (!isOpen) return null;

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
        className="relative z-10 flex max-h-[85vh] w-full max-w-md flex-col rounded-t-2xl border-t border-line bg-elevated pb-[max(16px,env(safe-area-inset-bottom))] pt-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-line" />

        <div className="flex items-center justify-between px-5">
          <div>
            <h3 className="text-lg font-semibold">替换动作</h3>
            <p className="mt-0.5 text-xs text-muted">
              当前：<span className="font-medium text-ink line-through">{currentTitle}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="pressable rounded-md px-2 py-1 text-sm font-semibold text-muted hover:text-ink"
          >
            ✕
          </button>
        </div>

        {data?.banned_injuries && data.banned_injuries.length > 0 && (
          <div className="mx-5 mt-3 rounded-lg bg-accent/15 px-3 py-1.5 text-[11px] font-medium text-accent-ink">
            伤痛防护：已按「{data.banned_injuries.join("、")}」剔除高风险动作
          </div>
        )}

        <div className="px-5 pt-3">
          <input
            type="text"
            className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none placeholder:text-muted focus:border-ink"
            placeholder={`搜索${muscle}部替代动作，或输入新动作名…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="no-scrollbar flex gap-1.5 overflow-x-auto px-5 py-2.5">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`pressable shrink-0 rounded-full px-3 py-1 text-xs font-semibold transition-all ${
                activeCategory === cat
                  ? "bg-ink text-bg"
                  : "border border-line bg-bg text-muted"
              }`}
              onClick={() => setActiveCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="min-h-[220px] flex-1 divide-y divide-line overflow-y-auto overscroll-contain px-5">
          {loading && (
            <div className="flex h-36 items-center justify-center text-xs text-muted">
              加载动作库中…
            </div>
          )}

          {!loading && filteredItems.length === 0 && (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <p className="text-sm font-semibold text-muted">未找到匹配动作</p>
              {query.trim() && (
                <button
                  type="button"
                  className="pressable mt-3 rounded-md bg-accent px-4 py-2 text-xs font-bold text-accent-ink"
                  onClick={() => {
                    onSelect(query.trim());
                    onClose();
                  }}
                >
                  直接使用「{query.trim()}」
                </button>
              )}
            </div>
          )}

          {!loading &&
            filteredItems.map((item) => (
              <button
                key={item.name}
                type="button"
                onClick={() => {
                  onSelect(item.name, item.category);
                  onClose();
                }}
                className="pressable flex w-full cursor-pointer items-center justify-between py-3 text-left hover:bg-bg/50"
              >
                <div className="min-w-0 flex-1 pr-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-ink">{item.name}</span>
                    <span className="rounded bg-line/60 px-1.5 py-0.5 text-[10px] font-medium text-muted">
                      {item.category}
                    </span>
                  </div>
                  {item.tips && (
                    <p className="mt-0.5 line-clamp-1 text-xs text-muted">{item.tips}</p>
                  )}
                </div>
                <span className="shrink-0 rounded-md bg-accent/25 px-2.5 py-1 text-xs font-bold text-accent-ink">
                  替换
                </span>
              </button>
            ))}
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
