import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, ChevronRight, ClipboardList, Video } from "lucide-react";
import { api, fetchPlans } from "../lib/api";
import { planCadenceLabel, planCornerBadge, planMuscleLine } from "../lib/planCardMeta";
import { Sparkline } from "../components/dashboard/TrainingDashboard";
import type { DashboardPeriod } from "../components/dashboard/TrainingDashboard";
import { MuscleHeatmapCard } from "../components/dashboard/MuscleHeatmapCard";
import type { PlanTemplateCard, TrainingDashboard as DashboardData, TrainingSession } from "../types";

export function TrainingPage() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<DashboardPeriod>("week");

  const { data: sessions = [] } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=60"),
  });
  const { data: dashboard } = useQuery({
    queryKey: ["training-dashboard", period],
    queryFn: () => api<DashboardData>(`/api/training/dashboard?period=${period}`),
    placeholderData: (previous) => previous,
  });
  const { data: plansData } = useQuery({
    queryKey: ["plans", "training-preview"],
    queryFn: () => fetchPlans({}),
  });

  const periodDates = useMemo(() => {
    if (!dashboard) return new Set<string>();
    return new Set(dashboard.week.days.map((day) => day.date));
  }, [dashboard]);

  const periodSessions = useMemo(
    () =>
      sessions.filter(
        (item) =>
          (item.status === "done" || item.status === "active") && periodDates.has(item.session_date),
      ),
    [sessions, periodDates],
  );

  const metrics = useMemo(() => {
    const doneSets = periodSessions.flatMap((item) => item.sets.filter((set) => set.completed));
    const minutes = periodSessions.reduce(
      (sum, item) => sum + (item.duration_minutes != null && item.duration_minutes >= 1 ? item.duration_minutes : 0),
      0,
    );
    const moves = new Set(doneSets.map((set) => set.exercise_name)).size;
    const prLifts = (dashboard?.key_lifts || []).filter((lift) => lift.is_pr);
    return {
      minutes,
      sets: doneSets.length,
      moves,
      sessionCount: periodSessions.filter((item) => item.status === "done").length,
      prCount: prLifts.length,
      prLabel: prLifts[0] ? `${shortName(prLifts[0].exercise_name)} ${prLifts[0].load}` : null,
    };
  }, [periodSessions, dashboard]);

  const previewPlans = (plansData?.items ?? []).slice(0, 2);
  const keyLifts = (dashboard?.key_lifts || []).slice(0, 3);
  const hasOverview = Boolean(dashboard && (dashboard.week.trained_days > 0 || metrics.sets > 0 || metrics.minutes > 0));

  return (
    <div className="flex min-h-full flex-col px-5 pb-6 pt-4 rise-in">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Gym Coach</p>
      <div className="mt-1.5 flex items-center justify-between gap-3">
        <h1 className="font-display text-[28px] font-extrabold tracking-tight">训练</h1>
        <div className="flex rounded-[10px] bg-[color-mix(in_srgb,var(--line)_80%,transparent)] p-[3px]">
          {(["week", "month"] as const).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setPeriod(item)}
              className={`pressable rounded-lg px-3 py-1 text-[11.5px] font-bold ${
                period === item ? "bg-elevated text-ink shadow-sm" : "text-muted"
              }`}
            >
              {item === "week" ? "周" : "月"}
            </button>
          ))}
        </div>
      </div>

      {/* 本周/月概览 */}
      <SectionHead title={period === "month" ? "本月概览" : "本周概览"} />
      {dashboard && hasOverview ? (
        <div className="border-t border-line">
          <div className="flex items-center gap-3.5 py-2">
            <WeekRing trained={dashboard.week.trained_days} target={dashboard.week.target_days || 3} />
            <div className="min-w-0 flex-1">
              <p className="text-[10.5px] font-semibold text-muted">
                {period === "month" ? "本月训练" : "本周训练"}
              </p>
              <p className="mt-0.5 text-[14px] font-extrabold leading-snug">{dashboard.headline}</p>
            </div>
          </div>
          <div className="flex border-t border-line">
            <Metric
              label="训练时长"
              value={metrics.minutes > 0 ? String(metrics.minutes) : null}
              unit="分钟"
              sub={
                metrics.sessionCount > 0
                  ? `${metrics.sessionCount} 场`
                  : null
              }
            />
            <Metric
              label="完成组数"
              value={metrics.sets > 0 ? String(metrics.sets) : null}
              unit="组"
              sub={metrics.moves > 0 ? `${metrics.moves} 个动作` : null}
            />
            <Metric
              label={period === "month" ? "本月 PR" : "本周 PR"}
              value={metrics.prCount > 0 ? String(metrics.prCount) : null}
              unit="个"
              sub={metrics.prLabel}
              subTone="up"
            />
          </div>
        </div>
      ) : (
        <p className="border-t border-line py-3 text-[13px] text-muted">
          {period === "month" ? "本月还没练，去今日页开一场吧。" : "本周还没练，去今日页开一场吧。"}
        </p>
      )}

      <SectionHead title="近期部位分布" />
      <MuscleHeatmapCard pulse={dashboard?.muscle_pulse} />

      {/* 计划库预览 */}
      <SectionHead title="计划库" more="全部 ›" onMore={() => navigate("/plans")} />
      {previewPlans.length > 0 ? (
        <div className="flex gap-2.5">
          {previewPlans.map((plan, index) => (
            <PlanPreviewCard key={plan.id} plan={plan} alt={index % 2 === 1} />
          ))}
        </div>
      ) : (
        <p className="text-[13px] text-muted">暂无已发布计划</p>
      )}

      {/* 主力动作进阶 */}
      <SectionHead
        title="主力动作进阶"
        more={keyLifts.length > 0 ? "全部 ›" : undefined}
        onMore={() => navigate("/training/lifts")}
      />
      {keyLifts.length > 0 ? (
        <div className="border-t border-line">
          {keyLifts.map((lift) => (
            <button
              key={lift.exercise_name}
              type="button"
              onClick={() => navigate(`/training/exercise/${encodeURIComponent(lift.exercise_name)}`)}
              className="pressable flex w-full items-center gap-3 border-b border-line py-2 text-left last:border-b-0"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-[13.5px] font-bold">
                  <span className="truncate">{lift.exercise_name}</span>
                  {lift.is_pr && (
                    <span className="rounded bg-ink px-1 py-0.5 text-[9px] font-extrabold text-[color:var(--accent-ink,#ece7fb)]">
                      PR
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[10.5px] text-muted">
                  {[lift.muscle, lift.load].filter(Boolean).join(" · ")}
                </p>
              </div>
              <Sparkline values={lift.history} />
              <ChevronRight size={16} className="shrink-0 text-muted/50" />
            </button>
          ))}
        </div>
      ) : (
        <p className="border-t border-line py-3 text-[13px] text-muted">练过几次后，这里会出现主力动作走势。</p>
      )}

      {/* 训练资源 */}
      <SectionHead title="训练资源" />
      <div className="border-t border-line">
        <ResourceRow
          icon={<BookOpen size={18} />}
          title="动作库"
          sub="要领示范"
          onClick={() => navigate("/exercises")}
        />
        <ResourceRow
          icon={<ClipboardList size={18} />}
          title="训练记录"
          sub="全部场次与小结"
          onClick={() => navigate("/training/records")}
        />
        <ResourceRow
          icon={<Video size={18} />}
          title="动作分析"
          sub="练后复盘"
          soon
          disabled
        />
      </div>
    </div>
  );
}

function SectionHead({
  title,
  more,
  onMore,
}: {
  title: string;
  more?: string;
  onMore?: () => void;
}) {
  return (
    <div className="mb-1.5 mt-3 flex items-center justify-between">
      <p className="text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">{title}</p>
      {more && onMore && (
        <button type="button" onClick={onMore} className="pressable text-[11.5px] font-bold text-accent-text">
          {more}
        </button>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  unit,
  sub,
  subTone = "flat",
}: {
  label: string;
  value: string | null;
  unit: string;
  sub?: string | null;
  subTone?: "up" | "flat";
}) {
  return (
    <div className="min-w-0 flex-1 border-l border-line px-3.5 py-2 first:border-l-0 first:pl-1">
      <p className="text-[10.5px] font-semibold text-muted">{label}</p>
      {value != null ? (
        <p className="font-num mt-0.5 text-[17px] font-extrabold tracking-tight">
          {value}
          <small className="ml-0.5 text-[10px] font-semibold text-muted">{unit}</small>
        </p>
      ) : (
        <p className="mt-0.5 text-[13px] font-bold text-muted">—</p>
      )}
      {sub && (
        <p className={`mt-0.5 text-[10px] font-bold ${subTone === "up" ? "text-ok" : "text-muted"}`}>
          {sub}
        </p>
      )}
    </div>
  );
}

function WeekRing({ trained, target }: { trained: number; target: number }) {
  const pct = target > 0 ? Math.min(trained / target, 1) : 0;
  const R = 19;
  const C = 2 * Math.PI * R;
  const filled = C * pct;
  return (
    <div className="relative h-14 w-14 shrink-0">
      <svg width="56" height="56" viewBox="0 0 48 48" className="-rotate-90">
        <circle cx="24" cy="24" r={R} stroke="var(--line)" strokeWidth="5" fill="none" />
        <circle
          cx="24"
          cy="24"
          r={R}
          stroke="var(--accent)"
          strokeWidth="5"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${C - filled}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-num text-[15px] font-extrabold leading-none">{trained}</span>
        <span className="mt-0.5 text-[8.5px] font-semibold text-muted">/ {target} 天</span>
      </div>
    </div>
  );
}

function PlanPreviewCard({ plan, alt }: { plan: PlanTemplateCard; alt?: boolean }) {
  const badge = planCornerBadge(plan);
  const muscles = planMuscleLine(plan);
  const cadence = planCadenceLabel(plan);
  const muscleChips = (plan.muscle_tags || []).map((t) => String(t).trim()).filter(Boolean).slice(0, 3);
  return (
    <Link
      to={`/plans/${encodeURIComponent(plan.id)}`}
      className="pressable flex h-[140px] min-w-0 flex-1 flex-col overflow-hidden rounded-[18px] p-3 text-white"
      style={
        plan.cover_url
          ? {
              backgroundImage: `linear-gradient(165deg, rgba(23,22,28,.28) 0%, rgba(23,22,28,.88) 72%), url(${plan.cover_url})`,
              backgroundSize: "cover",
              backgroundPosition: "center",
            }
          : {
              background: alt
                ? "linear-gradient(165deg, #3b2f54 0%, #1d1830 72%)"
                : "linear-gradient(165deg, #342c46 0%, #17161c 72%)",
            }
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
        <p className="truncate text-[16px] font-extrabold tracking-tight">{plan.title}</p>
        {muscles && muscleChips.length === 0 ? (
          <p className="mt-0.5 truncate text-[10.5px] font-medium text-white/72">{muscles}</p>
        ) : null}
        <div className="mt-1.5 flex flex-wrap gap-1">
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

function ResourceRow({
  icon,
  title,
  sub,
  onClick,
  soon,
  disabled,
}: {
  icon: ReactNode;
  title: string;
  sub: string;
  onClick?: () => void;
  soon?: boolean;
  disabled?: boolean;
}) {
  const Tag = onClick && !disabled ? "button" : "div";
  return (
    <Tag
      type={onClick && !disabled ? "button" : undefined}
      onClick={onClick && !disabled ? onClick : undefined}
      className={`flex w-full items-center gap-3 border-b border-line py-2 text-left last:border-b-0 ${
        disabled ? "opacity-55" : onClick ? "pressable" : ""
      }`}
    >
      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-line bg-elevated text-accent-text">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-bold">{title}</p>
        <p className="mt-0.5 text-[10.5px] text-muted">{sub}</p>
      </div>
      {soon ? (
        <span className="rounded-md border border-dashed border-line px-1.5 py-0.5 text-[9px] font-bold text-muted">
          即将上线
        </span>
      ) : (
        <ChevronRight size={16} className="shrink-0 text-muted/50" />
      )}
    </Tag>
  );
}

function shortName(name: string) {
  return name.length > 6 ? name.slice(0, 6) : name;
}
