import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, Search } from "lucide-react";
import { fetchPlans } from "../lib/api";
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
                <div className="grid grid-cols-2 gap-2.5">
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
  const muscles = (plan.muscle_tags || []).slice(0, 3);
  const meta = [plan.scene_tag, plan.level_label].filter(Boolean).join(" · ");
  const rhythm =
    plan.split_summary ||
    (plan.days_per_week ? `${plan.block_count ?? plan.days_per_week} 个板块` : null);
  return (
    <Link
      to={`/plans/${encodeURIComponent(plan.id)}`}
      className="pressable relative flex min-h-[148px] flex-col overflow-hidden rounded-2xl p-3 text-white"
      style={
        plan.cover_url
          ? {
              backgroundImage: `linear-gradient(165deg, rgba(23,22,28,.3) 0%, rgba(23,22,28,.9) 75%), url(${plan.cover_url})`,
              backgroundSize: "cover",
              backgroundPosition: "center",
            }
          : { background: "linear-gradient(165deg, #342c46 0%, #17161c 72%)" }
      }
    >
      {meta && (
        <span className="self-start rounded-md bg-white/15 px-2 py-0.5 text-[9.5px] font-bold">
          {meta}
        </span>
      )}
      <p className="mt-auto text-[16px] font-extrabold leading-snug tracking-tight">{plan.title}</p>
      <p className="mt-1 line-clamp-2 text-[10.5px] text-white/70">
        {[plan.badge_label || "教练编排", plan.level_label, rhythm].filter(Boolean).join(" · ")}
      </p>
      {muscles.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {muscles.map((tag) => (
            <span
              key={tag}
              className="rounded border border-white/25 px-1.5 py-0.5 text-[9px] font-bold text-white/85"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}

function groupPlans(items: PlanTemplateCard[]) {
  const map = new Map<string, PlanTemplateCard[]>();
  for (const plan of items) {
    const key = plan.scene_tag || plan.badge_label || "全部计划";
    const list = map.get(key) || [];
    list.push(plan);
    map.set(key, list);
  }
  return Array.from(map.entries()).map(([title, groupItems]) => ({ title, items: groupItems }));
}
