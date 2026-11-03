import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { SessionDetailSheet } from "../components/training/SessionDetailSheet";
import { sessionFacts, sessionResultLine, sessionTitle, volumeTrend } from "../components/training/sessionStats";
import { TrendMark } from "../components/training/TrendMark";
import type { TrainingSession } from "../types";

export function TrainingRecordsPage() {
  const navigate = useNavigate();
  const [detailId, setDetailId] = useState<number | null>(null);
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=30"),
  });
  const detailSession = useMemo(
    () => sessions.find((item) => item.id === detailId) ?? null,
    [sessions, detailId],
  );

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <h1 className="font-display text-[26px] font-bold tracking-tight">训练记录</h1>

      {isLoading && <p className="mt-4 text-sm text-muted">加载中…</p>}
      {!isLoading && sessions.length === 0 && (
        <p className="mt-4 text-sm text-muted">还没有训练记录。</p>
      )}
      {sessions.length > 0 && (
      <ul className="mt-4 divide-y divide-line rounded-2xl border border-line bg-elevated">
        {sessions.map((session) => (
          <li key={session.id}>
            <button
              type="button"
              onClick={() => setDetailId(session.id)}
              className="pressable flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-bold">{sessionTitle(session)}</p>
                <p className="mt-0.5 text-[11px] text-muted">{sessionFacts(session)}</p>
                {sessionResultLine(session, sessions) && (
                  <p className="mt-0.5 truncate text-[11px] font-bold">{sessionResultLine(session, sessions)}</p>
                )}
              </div>
              <TrendMark trend={volumeTrend(session, sessions)} />
            </button>
          </li>
        ))}
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
