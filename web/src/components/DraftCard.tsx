import { useState } from "react";
import { api } from "../lib/api";
import type { CardBlock, CardItem, TrainingSession } from "../types";
import { MUSCLE_OPTIONS, rebuildSubtitle } from "../types";
import { ReorderItem, ReorderList } from "./ReorderList";
import { WeightStepper } from "./WeightStepper";
import { SwapExerciseModal } from "./SwapExerciseModal";

type Props = {
  card: CardBlock;
  onChange: (card: CardBlock) => void;
  onAdopted: (session: TrainingSession, confirmedCard: CardBlock) => void;
  /** 今日场次状态：已完成时默认不能再采纳 */
  todayStatus?: "none" | "active" | "done" | null;
};

function isLocked(status: string | undefined) {
  return status === "confirmed" || status === "expired";
}

export function DraftCard({ card, onChange, onAdopted, todayStatus = null }: Props) {
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newMuscle, setNewMuscle] = useState<string>("胸");
  const [editingId, setEditingId] = useState<string | null>(null);
  const locked = isLocked(card.status);
  const todayDone = todayStatus === "done";

  // 替换动作弹窗状态
  const [swapTarget, setSwapTarget] = useState<CardItem | null>(null);

  function updateItem(id: string, patch: Partial<CardItem>) {
    onChange({
      ...card,
      items: card.items.map((it) => {
        if (it.id !== id) return it;
        const next = { ...it, ...patch, meta: { ...it.meta, ...(patch.meta || {}) } };
        next.subtitle = rebuildSubtitle(next.meta);
        return next;
      }),
    });
  }

  function removeItem(id: string) {
    onChange({ ...card, items: card.items.filter((it) => it.id !== id) });
  }

  function reorderItems(ids: string[]) {
    const byId = new Map(card.items.map((it) => [it.id, it]));
    onChange({
      ...card,
      items: ids.flatMap((id) => {
        const row = byId.get(id);
        return row ? [row] : [];
      }),
    });
  }

  function handleSwap(item: CardItem) {
    setSwapTarget(item);
  }

  function onSelectReplacement(newTitle: string) {
    if (!swapTarget) return;
    updateItem(swapTarget.id, {
      title: newTitle,
      meta: { ...swapTarget.meta, exercise: newTitle },
    });
    setSwapTarget(null);
  }

  function addCustom() {
    const name = newName.trim();
    if (!/^[\u4e00-\u9fffA-Za-z].{0,20}$/.test(name) || !/[\u4e00-\u9fffA-Za-z]{2,}/.test(name)) {
      alert("动作名用中文或英文，至少两个字，不要只填数字。");
      return;
    }
    const id = `custom-${Date.now()}`;
    const meta = { sets: 3, reps: "10", muscle: newMuscle };
    onChange({
      ...card,
      items: [
        ...card.items,
        { id, title: name, subtitle: rebuildSubtitle(meta), meta, selected: true },
      ],
    });
    setNewName("");
    setAdding(false);
  }

  async function adopt(forceReplaceDone = false) {
    const selected = card.items.filter((i) => i.selected);
    if (!selected.length) {
      alert("至少勾选一个动作再采纳");
      return;
    }
    if (todayDone && !forceReplaceDone) {
      return;
    }
    if (todayDone && forceReplaceDone) {
      const ok = confirm(
        "今日训练已经完成并生成总结。再次采纳会覆盖今天的场次（原记录作废）。确定吗？",
      );
      if (!ok) return;
    }
    setBusy(true);
    try {
      const session = await api<TrainingSession>("/api/training/adopt", {
        method: "POST",
        body: JSON.stringify({
          title: card.title,
          split_label: card.title.includes("·")
            ? card.title.split("·").pop()?.trim()
            : card.title.replace(/训$/, "") || null,
          items: selected,
          replace_today: true,
          force_replace_done: forceReplaceDone,
        }),
      });
      sessionStorage.removeItem("last_reply");
      const confirmedCard: CardBlock = {
        ...card,
        status: "confirmed",
        actions: [],
        meta: {
          ...card.meta,
          adopted_at: new Date().toISOString(),
          adopted_session_id: session.id,
        },
      };
      onAdopted(session, confirmedCard);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (locked) {
    const selected = card.items.filter((i) => i.selected);
    const label = card.status === "expired" ? "昨日草稿已失效" : "已采纳";
    return (
      <div className="rounded-xl border border-line bg-elevated/80 p-4 opacity-90">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-display text-base font-bold text-muted">{card.title}</h2>
          <span className="rounded bg-line px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-muted">
            {label}
          </span>
        </div>
        <ul className="mt-2 space-y-1 text-xs text-muted">
          {(selected.length ? selected : card.items).slice(0, 6).map((it) => (
            <li key={it.id}>
              · {it.title}
              {it.subtitle ? ` · ${it.subtitle}` : ""}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-muted">
          {card.status === "expired"
            ? "请重新跟教练说今天想练什么。"
            : "已进入今日执行；如需改计划，请新开一版草稿。"}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="rounded-xl border border-line bg-elevated p-4 shadow-[0_12px_40px_rgba(18,20,15,0.08)] pop-in">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid h-2 w-2 rounded-full bg-accent animate-pulse" />
            <h2 className="font-display text-lg font-bold">{card.title}</h2>
          </div>
          <span className="rounded bg-accent/20 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-accent-ink">
            可定制草稿
          </span>
        </div>
        <p className="mt-1 text-xs text-muted">按住左侧把手拖动排序，难的放前面 · 点 ⟳ 换动作</p>

        <ReorderList
          ids={card.items.map((it) => it.id)}
          labelOf={(id) => card.items.find((it) => it.id === id)?.title ?? ""}
          onReorder={reorderItems}
          className="mt-3 divide-y divide-line"
        >
          {card.items.map((it) => {
            const sets = Number(it.meta.sets ?? 3);
            const reps = String(it.meta.reps ?? "10");
            const weight = it.meta.weight != null ? Number(it.meta.weight) : null;
            const open = editingId === it.id;
            return (
              <ReorderItem key={it.id} id={it.id} className="py-3">
                <div className="flex items-start gap-3">
                  <button
                    type="button"
                    aria-label="选入计划"
                    className={`mt-1 grid h-5 w-5 shrink-0 place-items-center rounded-[4px] border-[1.5px] transition-colors ${
                      it.selected ? "border-accent-ink bg-accent text-accent-ink font-bold text-xs" : "border-line bg-bg"
                    }`}
                    onClick={() => updateItem(it.id, { selected: !it.selected })}
                  >
                    {it.selected ? "✓" : ""}
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-display text-sm font-bold text-ink">{it.title}</span>
                      <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] text-muted">
                        {String(it.meta.muscle || "常用")}
                      </span>
                    </div>

                    <button
                      type="button"
                      className="mt-1 flex items-center gap-1 text-left text-xs font-semibold text-muted hover:text-ink"
                      onClick={() => setEditingId(open ? null : it.id)}
                    >
                      <span>{it.subtitle || rebuildSubtitle(it.meta)}</span>
                      <span className="text-[10px] text-accent-ink/70">
                        {open ? "▲ 收起" : "▼ 调重量/组数"}
                      </span>
                    </button>

                    {/* 展开的微调控制区：无键盘交互，极佳手机操作体验 */}
                    {open && (
                      <div className="mt-2.5 rounded-lg border border-line bg-bg/70 p-2.5 space-y-2">
                        {/* 重量滑动选择与步进 */}
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-muted">目标重量:</span>
                          <WeightStepper
                            value={weight}
                            step={2.5}
                            label={`${it.title} 目标重量`}
                            onChange={(val) => {
                              const meta = { ...it.meta } as Record<string, unknown>;
                              if (val == null) delete meta.weight;
                              else meta.weight = val;
                              updateItem(it.id, { meta });
                            }}
                          />
                        </div>

                        {/* 组数步进 */}
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-muted">计划组数:</span>
                          <div className="inline-flex items-center rounded-lg border border-line bg-elevated p-0.5">
                            <button
                              type="button"
                              onClick={() =>
                                updateItem(it.id, {
                                  meta: { ...it.meta, sets: Math.max(1, sets - 1) },
                                })
                              }
                              className="pressable grid h-6 w-6 place-items-center rounded-md text-xs font-bold text-muted hover:text-ink"
                            >
                              -
                            </button>
                            <span className="min-w-[40px] text-center font-display text-xs font-bold">
                              {sets} 组
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                updateItem(it.id, {
                                  meta: { ...it.meta, sets: Math.min(10, sets + 1) },
                                })
                              }
                              className="pressable grid h-6 w-6 place-items-center rounded-md text-xs font-bold text-muted hover:text-ink"
                            >
                              +
                            </button>
                          </div>
                        </div>

                        {/* 次数快捷选择 */}
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-muted">每组次数:</span>
                          <div className="flex gap-1">
                            {["6-8", "8-10", "10-12", "12-15", "力竭"].map((r) => (
                              <button
                                key={r}
                                type="button"
                                className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                  reps === r
                                    ? "bg-accent font-extrabold text-accent-ink"
                                    : "border border-line bg-elevated text-muted"
                                }`}
                                onClick={() =>
                                  updateItem(it.id, {
                                    meta: { ...it.meta, reps: r },
                                  })
                                }
                              >
                                {r}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex shrink-0 items-center gap-1 pt-0.5">
                    <button
                      type="button"
                      title="在动作库中挑选替换"
                      className="pressable flex items-center gap-0.5 rounded-md border border-line bg-bg px-2 py-1 text-xs font-bold text-ink hover:bg-elevated"
                      onClick={() => handleSwap(it)}
                    >
                      <span>⟳</span>
                      <span className="text-[10px]">换</span>
                    </button>
                    <button
                      type="button"
                      title="移除此动作"
                      className="pressable rounded-md border border-line bg-bg px-2 py-1 text-xs font-bold text-muted hover:text-danger"
                      onClick={() => removeItem(it.id)}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </ReorderItem>
            );
          })}
        </ReorderList>

        {adding ? (
          <div className="mt-3 space-y-2">
            <input
              className="w-full rounded-md border border-line bg-bg px-3 py-2 text-xs outline-none"
              placeholder="输入自定义动作名..."
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addCustom()}
              autoFocus
            />
            <p className="text-[11px] font-bold text-muted">部位</p>
            <div className="flex flex-wrap gap-1.5">
              {MUSCLE_OPTIONS.map((m) => (
                <button
                  key={m}
                  type="button"
                  className={`rounded-md border px-2 py-1 text-[11px] font-bold ${
                    newMuscle === m ? "border-ink bg-ink text-bg" : "border-line bg-bg text-ink"
                  }`}
                  onClick={() => setNewMuscle(m)}
                >
                  {m}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="rounded-md bg-accent px-3 py-2 font-display text-xs font-bold text-accent-ink"
              onClick={addCustom}
            >
              添加
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="mt-3 flex items-center gap-1 text-xs font-bold text-muted hover:text-ink"
            onClick={() => setAdding(true)}
          >
            <span>＋</span>
            <span>添加自定义动作</span>
          </button>
        )}

        {todayDone ? (
          <div className="mt-4 space-y-2">
            <div className="rounded-lg border border-line bg-bg px-3 py-3 text-center">
              <p className="font-display text-sm font-extrabold">今日已完成</p>
              <p className="mt-1 text-[11px] text-muted">
                不能直接再采纳进今日。若真要重开一场，需明确覆盖。
              </p>
            </div>
            <button
              type="button"
              disabled={busy || !card.items.some((i) => i.selected)}
              onClick={() => void adopt(true)}
              className="pressable w-full rounded-lg border border-line py-3 text-xs font-bold text-muted disabled:opacity-50"
            >
              {busy ? "处理中…" : "覆盖今日已完成场次并重新采纳"}
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={busy || !card.items.some((i) => i.selected)}
            onClick={() => void adopt(false)}
            className="pressable mt-4 w-full rounded-lg bg-accent py-3.5 font-display text-sm font-extrabold text-accent-ink shadow-md disabled:opacity-50"
          >
            {busy ? "正在采纳生成今日日程…" : "采纳 · 进入今日执行"}
          </button>
        )}
      </div>

      {/* 换动作抽屉弹窗 */}
      {swapTarget && (
        <SwapExerciseModal
          isOpen={Boolean(swapTarget)}
          currentTitle={swapTarget.title}
          muscle={String(swapTarget.meta.muscle || "胸")}
          onClose={() => setSwapTarget(null)}
          onSelect={onSelectReplacement}
        />
      )}
    </>
  );
}
