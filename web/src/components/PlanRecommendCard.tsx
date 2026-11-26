import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { followPlan, fetchFollowing } from "../lib/api";
import type { CardBlock } from "../types";

type Props = {
  card: CardBlock;
};

function planIdOf(item: CardBlock["items"][number]): string | null {
  const meta = item.meta || {};
  if (typeof meta.plan_id === "string" && meta.plan_id.trim()) return meta.plan_id.trim();
  const raw = String(item.id || "");
  if (raw.startsWith("plan-")) return raw.slice(5) || null;
  return raw || null;
}

export function PlanRecommendCard({ card }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState<string | null>(null);

  async function onFollow(planId: string, title: string) {
    if (!planId || busyId) return;
    setBusyId(planId);
    try {
      const current = await fetchFollowing();
      if (current.active_plan_id && current.active_plan_id !== planId) {
        const currentTitle = current.plan?.title || current.active_plan_id;
        const ok = window.confirm(
          `将切换跟练计划为「${title}」（当前：${currentTitle}）。原计划历史保留，今日已有场次不会被自动覆盖。确定吗？`,
        );
        if (!ok) return;
      }
      await followPlan(planId);
      void qc.invalidateQueries({ queryKey: ["plans-following"] });
      void qc.invalidateQueries({ queryKey: ["plans"] });
      navigate(`/plans/${encodeURIComponent(planId)}`);
    } catch (e) {
      alert(e instanceof Error ? e.message : "加入跟练失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="rounded-lg border border-line bg-elevated p-3.5 shadow-card">
      <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">可跟计划</p>
      <h3 className="mt-1 font-display text-[17px] font-extrabold tracking-tight text-ink">
        {card.title || "为你挑了几套计划"}
      </h3>
      <ul className="mt-3 space-y-2.5">
        {card.items.map((item) => {
          const planId = planIdOf(item);
          const cover =
            typeof item.meta?.cover_url === "string" ? item.meta.cover_url : null;
          const scene =
            typeof item.meta?.scene_tag === "string" ? item.meta.scene_tag : null;
          return (
            <li
              key={item.id}
              className="overflow-hidden rounded-[14px] border border-line bg-bg"
            >
              <div className="flex gap-3 p-2.5">
                <div className="h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br from-[var(--hero-a)] to-elevated">
                  {cover ? (
                    <img src={cover} alt="" className="h-full w-full object-cover" />
                  ) : null}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-extrabold text-ink">{item.title}</p>
                  {item.subtitle ? (
                    <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-relaxed text-muted">
                      {item.subtitle}
                    </p>
                  ) : null}
                  {scene ? (
                    <p className="mt-1 text-[10.5px] font-bold text-accent-text">{scene}</p>
                  ) : null}
                </div>
              </div>
              <div className="flex gap-2 border-t border-line px-2.5 py-2">
                <button
                  type="button"
                  disabled={!planId || Boolean(busyId)}
                  className="pressable flex-1 rounded-[10px] border border-line bg-elevated py-2 text-[12px] font-bold text-ink disabled:opacity-50"
                  onClick={() => {
                    if (planId) navigate(`/plans/${encodeURIComponent(planId)}`);
                  }}
                >
                  查看详情
                </button>
                <button
                  type="button"
                  disabled={!planId || Boolean(busyId)}
                  className="pressable flex-1 rounded-[10px] bg-accent py-2 text-[12px] font-extrabold text-accent-ink disabled:opacity-50"
                  onClick={() => {
                    if (planId) void onFollow(planId, item.title);
                  }}
                >
                  {busyId === planId ? "加入中…" : "加入跟练"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
