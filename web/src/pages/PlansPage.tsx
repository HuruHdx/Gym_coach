import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, Search } from "lucide-react";
import { fetchPlans } from "../lib/api";
import { planCadenceLabel, planCornerBadge, planMuscleLine } from "../lib/planCardMeta";
import type { PlanTemplateCard } from "../types";

export function PlansPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<"train" | "nutrition">("train");
  const [scene, setScene] = useState("全部");
  const [q, setQ] = useState("");

  const query = useQuery({
    queryKey: ["plans", "all"],
    queryFn: () => fetchPlans({}),
  });

  const allItems = query.data?.items ?? [];
  const sceneChips = useMemo(() => {
    const tags = new Set<string>();
    for (const plan of allItems) {
      if (plan.scene_tag) tags.add(plan.scene_tag);
    }
    return ["全部", ...Array.from(tags)];
  }, [allItems]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return allItems.filter((plan) => {
      if (scene !== "全部" && plan.scene_tag !== scene) return false;
      if (!needle) return true;
      const hay = [
        plan.title,
        plan.subtitle,
        plan.split_summary,
        plan.badge_label,
        plan.scene_tag,
        ...(plan.muscle_tags || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(needle);
    });
  }, [allItems, scene, q]);

  const groups = useMemo(() => groupPlans(filtered), [filtered]);

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="pressable -ml-1 mb-1 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
      >
        <ChevronLeft size={16} />
        返回
      </button>
      <h1 className="font-display text-[26px] font-extrabold tracking-tight">计划库</h1>

      <label className="mt-3 flex items-center gap-2 rounded-xl border border-line bg-elevated px-3.5 py-2.5">
        <Search size={16} className="shrink-0 text-muted" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜索训练计划"
          className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
        />
      </label>

      <div className="mt-3 flex rounded-[10px] bg-[color-mix(in_srgb,var(--line)_80%,transparent)] p-[3px]">
        <button
          type="button"
          onClick={() => setTab("train")}
          className={`pressable flex-1 rounded-lg py-1.5 text-[12px] font-bold ${
            tab === "train" ? "bg-elevated text-ink shadow-sm" : "text-muted"
          }`}
        >
          锻炼
        </button>
        <button
          type="button"
          onClick={() => setTab("nutrition")}
          className={`pressable relative flex-1 rounded-lg py-1.5 text-[12px] font-bold ${
            tab === "nutrition" ? "bg-elevated text-ink shadow-sm" : "text-muted"
          }`}
        >
          营养计划
          <span className="ml-1 rounded border border-dashed border-line px-1 py-0.5 text-[9px] font-bold text-muted">
            后期
          </span>
        </button>
      </div>

      {tab === "nutrition" ? (
        <p className="mt-8 text-center text-sm text-muted">营养计划后期再接，饮食问答先走教练页。</p>
      ) : (
        <>
          <div className="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto pb-1">
            {sceneChips.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setScene(item)}
                className={`shrink-0 rounded-lg px-3 py-1.5 text-[11.5px] font-bold ${
                  scene === item
                    ? "bg-ink text-[color:var(--accent-ink,#fff)]"
                    : "border border-line bg-elevated text-muted"
                }`}
              >
                {item}
              </button>
            ))}
          </div>

          {query.isLoading && <p className="mt-4 text-sm text-muted">加载中…</p>}
          {query.isError && <p className="mt-4 text-sm text-danger">加载失败，请稍后重试。</p>}
          {!query.isLoading && !query.isError && filtered.length === 0 && (
            <p className="mt-8 text-center text-sm text-muted">
              {allItems.length === 0 ? "暂无已发布计划" : "没有符合条件的计划"}
            </p>
          )}

          <div className="mt-4 space-y-5">
            {groups.map((group) => (
              <section key={group.title}>
                <p className="mb-2 text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">
                  {group.title}
                </p>
                <div className="no-scrollbar -mx-4 flex gap-2.5 overflow-x-auto px-4 pb-0.5">
                  {group.items.map((plan) => (
                    <PlanCard key={plan.id} plan={plan} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function PlanCard({ plan }: { plan: PlanTemplateCard }) {
  const badge = planCornerBadge(plan);
  const muscles = planMuscleLine(plan);
  const cadence = planCadenceLabel(plan);
  const muscleChips = (plan.muscle_tags || []).map((t) => String(t).trim()).filter(Boolean).slice(0, 3);
  return (
    <Link
      to={`/plans/${encodeURIComponent(plan.id)}`}
      className="pressable flex h-[176px] w-[156px] shrink-0 flex-col overflow-hidden rounded-2xl p-3 text-white"
      style={
        plan.cover_url
          ? {
              backgroundImage: `linear-gradient(165deg, rgba(23,22,28,.22) 0%, rgba(23,22,28,.88) 72%), url(${plan.cover_url})`,
              backgroundSize: "cover",
              backgroundPosition: "center",
            }
          : { background: "linear-gradient(165deg, #342c46 0%, #17161c 72%)" }
      }
    >
      {badge ? (
        <span className="max-w-full self-start truncate rounded-md bg-white/16 px-2 py-[3px] text-[10px] font-bold leading-none text-white">
          {badge}
        </span>
      ) : (
        <span className="h-[18px]" aria-hidden />
      )}
      <div className="mt-auto min-w-0">
        <p className="line-clamp-2 text-[17px] font-extrabold leading-snug tracking-tight">{plan.title}</p>
        {muscles && muscleChips.length === 0 ? (
          <p className="mt-1 line-clamp-1 text-[11px] font-medium text-white/72">{muscles}</p>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-1">
          {muscleChips.map((tag) => (
            <span
              key={tag}
              className="rounded border border-white/22 px-1.5 py-0.5 text-[9px] font-bold text-white/85"
            >
              {tag}
            </span>
          ))}
          <span className="rounded border border-white/22 px-1.5 py-0.5 text-[9px] font-bold text-white/85">
            {cadence}
          </span>
        </div>
      </div>
    </Link>
  );
}

function groupPlans(items: PlanTemplateCard[]) {
  const map = new Map<string, PlanTemplateCard[]>();
  for (const plan of items) {
    const key = plan.scene_tag || "热门计划";
    const list = map.get(key) || [];
    list.push(plan);
    map.set(key, list);
  }
  return Array.from(map.entries()).map(([title, groupItems]) => ({ title, items: groupItems }));
}
