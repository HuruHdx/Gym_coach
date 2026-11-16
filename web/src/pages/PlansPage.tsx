import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { fetchPlans } from "../lib/api";
import { MUSCLE_OPTIONS } from "../types";

const TYPE_FILTERS = [
  { id: "", label: "全部" },
  { id: "framework", label: "框架" },
  { id: "fixed", label: "成品" },
] as const;

const LEVEL_FILTERS = [
  { id: "全部", label: "全部难度" },
  { id: "beginner", label: "新手" },
  { id: "intermediate", label: "进阶" },
  { id: "advanced", label: "强化" },
] as const;

function typeLabel(t: string) {
  if (t === "framework") return "框架";
  if (t === "fixed") return "成品";
  return t;
}

export function PlansPage() {
  const navigate = useNavigate();
  const [type, setType] = useState<"" | "framework" | "fixed">("");
  const [muscle, setMuscle] = useState("全部");
  const [level, setLevel] = useState("全部");

  const query = useQuery({
    queryKey: ["plans", type, muscle, level],
    queryFn: () =>
      fetchPlans({
        type,
        muscle,
        level: level === "全部" ? "" : level,
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

      <div className="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto pb-1">
        {TYPE_FILTERS.map((item) => (
          <button
            key={item.id || "all"}
            type="button"
            onClick={() => setType(item.id)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-bold ${
              type === item.id ? "bg-accent text-accent-ink" : "border border-line bg-elevated text-muted"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="no-scrollbar mt-2 flex gap-1.5 overflow-x-auto pb-1">
        {["全部", ...MUSCLE_OPTIONS].map((item) => (
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

      <div className="no-scrollbar mt-2 flex gap-1.5 overflow-x-auto pb-1">
        {LEVEL_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setLevel(item.id)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-bold ${
              level === item.id ? "bg-accent text-accent-ink" : "border border-line bg-elevated text-muted"
            }`}
          >
            {item.label}
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
                  {plan.badge_label || typeLabel(plan.template_type)}
                </span>
                <span className="rounded-md border border-line bg-elevated/80 px-2 py-0.5 text-[10px] font-bold text-muted">
                  {typeLabel(plan.template_type)}
                </span>
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
