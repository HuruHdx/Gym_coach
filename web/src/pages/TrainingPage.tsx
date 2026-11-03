import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { api } from "../lib/api";
import { TrainingDashboard } from "../components/dashboard/TrainingDashboard";
import type { DashboardPeriod } from "../components/dashboard/TrainingDashboard";
import { SessionDetailSheet } from "../components/training/SessionDetailSheet";
import { sessionFacts, sessionResultLine, sessionTitle, volumeTrend } from "../components/training/sessionStats";
import { TrendMark } from "../components/training/TrendMark";
import type { TrainingDashboard as DashboardData, TrainingSession } from "../types";

export function TrainingPage() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState<DashboardPeriod>("week");
  const [detailId, setDetailId] = useState<number | null>(null);
  const openExercise = (name: string) => navigate(`/training/exercise/${encodeURIComponent(name)}`);

  const { data: sessions = [] } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=30"),
  });
  const { data: dashboard } = useQuery({
    queryKey: ["training-dashboard", period],
    queryFn: () => api<DashboardData>(`/api/training/dashboard?period=${period}`),
    placeholderData: (previous) => previous,
  });

  const latest = useMemo(
    () => sessions.find((item) => item.status === "done") ?? sessions[0] ?? null,
    [sessions],
  );
  const detailSession = useMemo(
    () => sessions.find((item) => item.id === detailId) ?? null,
    [sessions, detailId],
  );
  const activityLine = useMemo(() => {
    if (!dashboard) return null;
    const dates = new Set(dashboard.week.days.map((day) => day.date));
    const picked = sessions.filter(
      (item) => (item.status === "done" || item.status === "active") && dates.has(item.session_date),
    );
    const done = picked.flatMap((item) => item.sets.filter((set) => set.completed));
    if (done.length === 0) return null;
    const moves = new Set(done.map((set) => set.exercise_name)).size;
    const minutes = picked.reduce(
      (sum, item) => sum + (item.duration_minutes != null && item.duration_minutes >= 1 ? item.duration_minutes : 0),
      0,
    );
    const parts = [`${done.length} 组`];
    if (minutes > 0) parts.push(`${minutes} 分钟`);
    if (moves > 0) parts.push(`${moves} 个动作`);
    return parts.join(" · ");
  }, [dashboard, sessions]);

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <p className="font-display text-[11px] font-extrabold uppercase tracking-[0.12em] text-muted">
        Gym Coach
      </p>
      <h1 className="font-display text-[26px] font-bold tracking-tight">训练</h1>

      {dashboard && (
        <div className="mt-4">
          <TrainingDashboard
            data={dashboard}
            period={period}
            onPeriodChange={setPeriod}
            onOpenSession={setDetailId}
            onOpenExercise={openExercise}
            onSeeAllLifts={() => navigate("/training/lifts")}
            activityLine={activityLine}
          />
        </div>
      )}

      <section className="mt-3 rounded-2xl border border-line bg-elevated px-3.5 py-3.5">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold text-muted">最近一场</p>
          <Link
            to="/training/records"
            className="pressable inline-flex items-center text-[11px] font-extrabold text-muted"
          >
            全部记录
            <ChevronRight size={16} />
          </Link>
        </div>
        {!latest ? (
          <p className="mt-3 text-sm text-muted">完成一次训练后，这里会留下这场的摘要。</p>
        ) : (
          <button
            type="button"
            onClick={() => setDetailId(latest.id)}
            className="pressable mt-2 flex w-full items-center justify-between gap-3 text-left"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-bold">{sessionTitle(latest)}</p>
              <p className="mt-0.5 text-[11px] text-muted">{sessionFacts(latest)}</p>
              {sessionResultLine(latest, sessions) && (
                <p className="mt-0.5 truncate text-[11px] font-bold">{sessionResultLine(latest, sessions)}</p>
              )}
            </div>
            <TrendMark trend={volumeTrend(latest, sessions)} />
          </button>
        )}
      </section>

      {detailSession &&
        createPortal(
          <SessionDetailSheet
            session={detailSession}
            sessions={sessions}
            onClose={() => setDetailId(null)}
            onOpenExercise={(name) => {
              setDetailId(null);
              openExercise(name);
            }}
          />,
          document.body,
        )}
    </div>
  );
}
