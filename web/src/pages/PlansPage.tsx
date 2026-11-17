import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { fetchPlans } from "../lib/api";
import { MUSCLE_OPTIONS } from "../types";

const SCENE_FILTERS = [
  "全部",
  "三分化",
  "四分化",
  "博主同款",
  "单部位专项",
  "新手入门",
] as const;

export function PlansPage() {
  const navigate = useNavigate();
  const [scene, setScene] = useState<string>("全部");
  const [muscle, setMuscle] = useState("全部");

  const query = useQuery({
    queryKey: ["plans", scene, muscle],
    queryFn: () =>
      fetchPlans({
        scene,
        muscle,
      }),
  });

  const items = useMemo(() => query.data?.items ?? [], [query.data]);

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
      >
        <ChevronLeft size={16} />
        返回
      </button>

      <h1 className="font-display text-[26px] font-bold tracking-tight">训练计划</h1>
      <p className="mt-1 text-[12px] text-muted">
        {query.isLoading ? "加载中…" : `${items.length} 个已发布计划`}
      </p>

      <div className="chipbar no-scrollbar mt-3 flex gap-1.5 overflow-x-auto pb-1">
        {SCENE_FILTERS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setScene(item)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-bold ${
              scene === item ? "bg-accent text-accent-ink" : "border border-line bg-elevated text-muted"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="chipbar no-scrollbar mt-2 flex gap-1.5 overflow-x-auto pb-1">
        {["全部", ...MUSCLE_OPTIONS.filter((m) => m !== "全身" && m !== "核心")].map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setMuscle(item)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-bold ${
              muscle === item ? "bg-accent text-accent-ink" : "border border-line bg-elevated text-muted"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {query.isError && (
        <p className="mt-4 text-sm text-danger">加载失败，请稍后重试。</p>
      )}

      {!query.isLoading && !query.isError && items.length === 0 && (
        <p className="mt-8 text-center text-sm text-muted">暂无已发布计划</p>
      )}

      <div className="mt-4 grid gap-3">
        {items.map((plan) => (
          <Link
            key={plan.id}
            to={`/plans/${encodeURIComponent(plan.id)}`}
            className="pressable relative overflow-hidden rounded-2xl border border-line bg-elevated"
          >
            <div
              className="relative min-h-[132px] bg-gradient-to-br from-[var(--hero-a)] via-bg to-bg p-4"
              style={
                plan.cover_url
                  ? {
                      backgroundImage: `linear-gradient(to top, rgb(var(--bg-rgb) / 0.92), rgb(var(--bg-rgb) / 0.35)), url(${plan.cover_url})`,
                      backgroundSize: "cover",
                      backgroundPosition: "center",
                    }
                  : undefined
              }
            >
              <div className="flex items-start justify-between gap-2">
                <span className="rounded-md bg-tint px-2 py-0.5 text-[10px] font-extrabold text-accent-text">
                  {plan.badge_label || plan.scene_tag || "计划"}
                </span>
                {plan.scene_tag && (
                  <span className="rounded-md border border-line bg-elevated/80 px-2 py-0.5 text-[10px] font-bold text-muted">
                    {plan.scene_tag}
                  </span>
                )}
              </div>
              <h2 className="mt-6 font-display text-xl font-extrabold tracking-tight text-ink">
                {plan.title}
              </h2>
              <p className="mt-1 text-[12px] text-muted">
                {plan.split_summary || plan.subtitle || "—"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-4 py-2.5 text-[11px] text-muted">
              <span className="num">每周 {plan.days_per_week} 练</span>
              {plan.minutes_label && <span className="num">{plan.minutes_label}</span>}
              {plan.level_label && <span>{plan.level_label}</span>}
              {plan.author && <span>{plan.author}</span>}
            </div>
            {plan.muscle_tags?.length > 0 && (
              <div className="flex flex-wrap gap-1 px-4 pb-3">
                {plan.muscle_tags.slice(0, 6).map((tag) => (
                  <span
                    key={tag}
                    className="rounded-md border border-line bg-bg px-2 py-0.5 text-[10px] font-bold text-muted"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
