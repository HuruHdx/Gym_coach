import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../lib/api";
import { SessionDetailSheet } from "../components/training/SessionDetailSheet";
import {
  sessionFacts,
  sessionResultLine,
  sessionTitle,
  volumeTrend,
} from "../components/training/sessionStats";
import { TrendMark } from "../components/training/TrendMark";
import type { TrainingSession } from "../types";

export function TrainingRecordsPage() {
  const navigate = useNavigate();
  const [detailId, setDetailId] = useState<number | null>(null);
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=60"),
  });

  const recent = useMemo(() => {
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
    return sessions.filter((s) => {
      const t = Date.parse(`${s.session_date}T00:00:00`);
      return Number.isFinite(t) && t >= cutoff;
    });
  }, [sessions]);

  const overview = useMemo(() => {
    const done = recent.filter((s) => s.status === "done");
    const minutes = done.reduce(
      (sum, s) => sum + (s.duration_minutes != null && s.duration_minutes >= 1 ? s.duration_minutes : 0),
      0,
    );
    const doneSets = done.reduce((sum, s) => sum + (s.progress?.done || 0), 0);
    const totalSets = done.reduce((sum, s) => sum + (s.progress?.total || 0), 0);
    const rate = totalSets > 0 ? Math.round((doneSets / totalSets) * 100) : null;
    return {
      sessions: done.length,
      hours: minutes > 0 ? Math.round((minutes / 60) * 10) / 10 : null,
      rate,
    };
  }, [recent]);

  const detailSession = useMemo(
    () => sessions.find((item) => item.id === detailId) ?? null,
    [sessions, detailId],
  );

  const list = recent.length > 0 ? recent : sessions;

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/training"))}
        className="pressable -ml-1 mb-1 inline-flex h-9 w-fit items-center gap-1 rounded-lg px-1 text-[13px] font-bold text-ink"
        aria-label="返回"
      >
        <ArrowLeft size={18} strokeWidth={2.25} />
        返回
      </button>
      <h1 className="font-display text-[26px] font-extrabold tracking-tight">训练记录</h1>
      <p className="mt-1 text-[12px] text-muted">近 30 天</p>

      {(overview.sessions > 0 || overview.hours != null) && (
        <div className="mt-3 flex overflow-hidden rounded-2xl border border-line bg-elevated">
          <OverviewCell label="训练场次" value={`${overview.sessions}`} unit="场" />
          <OverviewCell
            label="总时长"
            value={overview.hours != null ? String(overview.hours) : "—"}
            unit={overview.hours != null ? "h" : ""}
          />
          <OverviewCell
            label="完成率"
            value={overview.rate != null ? String(overview.rate) : "—"}
            unit={overview.rate != null ? "%" : ""}
          />
        </div>
      )}

      {isLoading && <p className="mt-4 text-sm text-muted">加载中…</p>}
      {!isLoading && list.length === 0 && (
        <div className="mt-10 text-center">
          <p className="text-sm text-muted">还没有训练记录</p>
          <Link to="/" className="pressable mt-3 inline-block text-sm font-bold text-accent-text">
            去今日页开始第一场 ›
          </Link>
        </div>
      )}

      {list.length > 0 && (
        <ul className="mt-4 divide-y divide-line border-t border-line">
          {list.map((session) => {
            const result = sessionResultLine(session, sessions);
            const progress =
              session.progress?.total != null
                ? `${session.progress.done}/${session.progress.total} 组`
                : null;
            return (
              <li key={session.id}>
                <button
                  type="button"
                  onClick={() => setDetailId(session.id)}
                  className="pressable flex w-full items-start justify-between gap-3 py-3 text-left"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-bold">
                        {sessionTitle(session)}
                        <span className="text-muted"> · {session.session_date.slice(5)}</span>
                      </p>
                      {progress && (
                        <span className="shrink-0 text-[11px] font-bold text-muted">{progress}</span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted">
                      <span>{sessionFacts(session)}</span>
                      <TrendMark trend={volumeTrend(session, sessions)} />
                    </div>
                    {result && (
                      <p className="mt-1 truncate text-[11.5px] font-extrabold text-accent-text">
                        {result}
                      </p>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {detailSession &&
        createPortal(
          <SessionDetailSheet
            session={detailSession}
            sessions={sessions}
            onClose={() => setDetailId(null)}
            onOpenExercise={(name) => {
              setDetailId(null);
              navigate(`/training/exercise/${encodeURIComponent(name)}`);
            }}
          />,
          document.body,
        )}
    </div>
  );
}

function OverviewCell({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="min-w-0 flex-1 border-l border-line px-3 py-3 first:border-l-0">
      <p className="text-[10.5px] font-semibold text-muted">{label}</p>
      <p className="font-num mt-1 text-[18px] font-extrabold tracking-tight">
        {value}
        {unit && <small className="ml-0.5 text-[10px] font-semibold text-muted">{unit}</small>}
      </p>
    </div>
  );
}
