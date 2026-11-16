import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { DraftCard } from "../components/DraftCard";
import { api, expandPlan, fetchPlanDetail } from "../lib/api";
import type { CardBlock, PlanBlockDetail, TrainingSession } from "../types";

function typeLabel(t: string) {
  if (t === "framework") return "框架型";
  if (t === "fixed") return "成品型";
  return t;
}

export function PlanDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<CardBlock | null>(null);
  const [expandingId, setExpandingId] = useState<number | null>(null);

  const detailQuery = useQuery({
    queryKey: ["plan-detail", id],
    queryFn: () => fetchPlanDetail(id),
    enabled: Boolean(id),
  });

  const { data: todaySession } = useQuery({
    queryKey: ["training-today"],
    queryFn: () => api<TrainingSession | null>("/api/training/today"),
  });

  const todayStatus: "none" | "active" | "done" = !todaySession
    ? "none"
    : todaySession.status === "done"
      ? "done"
      : todaySession.status === "active"
        ? "active"
        : "none";

  const plan = detailQuery.data;
  const blocks = useMemo(() => plan?.blocks ?? [], [plan]);

  async function startBlock(block: PlanBlockDetail) {
    if (!id || expandingId != null) return;
    setExpandingId(block.id);
    try {
      const res = await expandPlan(id, block.id);
      setDraft(res.card);
      window.requestAnimationFrame(() => {
        document.getElementById("plan-draft")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (e) {
      alert(String(e));
    } finally {
      setExpandingId(null);
    }
  }

  if (detailQuery.isLoading) {
    return <div className="px-4 pt-8 text-sm text-muted">加载计划…</div>;
  }

  if (detailQuery.isError || !plan) {
    return (
      <div className="flex min-h-full flex-col px-4 pb-6 pt-3">
        <button
          type="button"
          onClick={() => navigate("/plans")}
          className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
        >
          <ChevronLeft size={16} />
          计划列表
        </button>
        <p className="mt-6 text-sm text-danger">计划不存在或未发布。</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate("/plans")}
        className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
      >
        <ChevronLeft size={16} />
        计划列表
      </button>

      <div
        className="relative overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-[var(--hero-a)] via-bg to-bg p-4"
        style={
          plan.cover_url
            ? {
                backgroundImage: `linear-gradient(to top, rgb(var(--bg-rgb) / 0.94), rgb(var(--bg-rgb) / 0.4)), url(${plan.cover_url})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }
            : undefined
        }
      >
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-md bg-tint px-2 py-0.5 text-[10px] font-extrabold text-accent-text">
            {plan.badge_label || typeLabel(plan.template_type)}
          </span>
          <span className="rounded-md border border-line bg-elevated/80 px-2 py-0.5 text-[10px] font-bold text-muted">
            {typeLabel(plan.template_type)}
          </span>
          {plan.level_label && (
            <span className="rounded-md border border-line bg-elevated/80 px-2 py-0.5 text-[10px] font-bold text-muted">
              {plan.level_label}
            </span>
          )}
        </div>
        <h1 className="mt-4 font-display text-[26px] font-extrabold tracking-tight">{plan.title}</h1>
        {plan.author && <p className="mt-1 text-[12px] text-muted">{plan.author}</p>}
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted">
          <span className="num">每周 {plan.days_per_week} 练</span>
          {plan.minutes_label && <span className="num">{plan.minutes_label}</span>}
          <span className="num">{blocks.length} 个板块</span>
        </div>
      </div>

      {plan.description && (
        <p className="mt-3 text-sm leading-relaxed text-muted">{plan.description}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {(plan.muscle_tags || []).map((tag) => (
          <span
            key={tag}
            className="rounded-md border border-line bg-elevated px-2 py-0.5 text-[10px] font-bold text-muted"
          >
            {tag}
          </span>
        ))}
        {(plan.gear_tags || []).map((tag) => (
          <span
            key={`g-${tag}`}
            className="rounded-md border border-line bg-bg px-2 py-0.5 text-[10px] font-bold text-muted"
          >
            {tag}
          </span>
        ))}
      </div>

      <p className="mt-5 text-xs font-bold text-muted">选一个板块练今天这场</p>
      <div className="mt-2 space-y-3">
        {blocks.map((block) => (
          <section key={block.id} className="rounded-xl border border-line bg-elevated p-3.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="font-display text-base font-bold tracking-tight">{block.title}</h2>
                <p className="mt-0.5 text-[11px] text-muted">
                  {(block.muscles || []).join(" · ") || "—"}
                  {block.minutes_label ? ` · ${block.minutes_label}` : ""}
                  {` · ${block.exercises.length} 个动作`}
                </p>
              </div>
              <button
                type="button"
                disabled={expandingId != null}
                onClick={() => void startBlock(block)}
                className="pressable shrink-0 rounded-md bg-accent px-3 py-2 text-[12px] font-extrabold text-accent-ink disabled:opacity-50"
              >
                {expandingId === block.id ? "展开中…" : "练这场"}
              </button>
            </div>

            {block.note && <p className="mt-2 text-[11px] text-muted">{block.note}</p>}

            <ul className="mt-3 space-y-2">
              {block.exercises.map((ex) => (
                <li
                  key={ex.id}
                  className="flex items-center gap-2.5 rounded-lg border border-line bg-bg px-2.5 py-2"
                >
                  <div className="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-md bg-tint text-[10px] font-bold text-accent-text">
                    {ex.thumb_url ? (
                      <img src={ex.thumb_url} alt="" className="h-full w-full object-cover" />
                    ) : (
                      (ex.exercise_name || ex.role_label || "动").slice(0, 2)
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold text-ink">
                      {ex.exercise_name || "待补充"}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted">
                      {ex.role_label || ex.role}
                      {ex.target_sets != null && ex.target_reps
                        ? ` · ${ex.target_sets}×${ex.target_reps}`
                        : ""}
                      {ex.warmup_sets ? ` · 热身 ${ex.warmup_sets}` : ""}
                      {ex.lock_level === "slot" ? " · 可换" : " · 锁定"}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      {draft && (
        <div id="plan-draft" className="mt-6 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-bold text-muted">今日草稿预览</p>
            <button
              type="button"
              className="text-xs font-bold text-accent-text"
              onClick={() => setDraft(null)}
            >
              收起
            </button>
          </div>
          <DraftCard
            card={draft}
            onChange={setDraft}
            todayStatus={todayStatus}
            onAdopted={() => {
              void qc.invalidateQueries({ queryKey: ["training-today"] });
              void qc.invalidateQueries({ queryKey: ["training-sessions"] });
              void qc.invalidateQueries({ queryKey: ["training-dashboard"] });
              navigate("/");
            }}
          />
        </div>
      )}

      <p className="mt-6 text-center text-[11px] text-muted">
        也可回{" "}
        <Link to="/coach" className="font-bold text-accent-text">
          教练
        </Link>{" "}
        用对话定制一场
      </p>
    </div>
  );
}
