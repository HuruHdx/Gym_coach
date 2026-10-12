import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { WeightTrendChart } from "../components/dashboard/WeightTrendChart";
import type { ExerciseStat, SetLog, TrainingSession } from "../types";

export function ExerciseTrendPage() {
  const { name: raw = "" } = useParams();
  const name = decodeName(raw);
  const navigate = useNavigate();

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=50"),
  });
  const { data: exercises = [] } = useQuery({
    queryKey: ["exercises"],
    queryFn: () => api<ExerciseStat[]>("/api/training/exercises"),
  });

  const stat = exercises.find((e) => e.name === name) ?? null;
  const history = useMemo(() => exerciseHistory(sessions, name), [sessions, name]);
  const chartPoints = useMemo(
    () =>
      [...history]
        .reverse()
        .filter((p): p is HistPoint & { weight: number } => p.weight != null)
        .map((p) => ({ date: p.date, weight: p.weight, reps: p.reps })),
    [history],
  );

  return (
    <div className="flex min-h-full flex-col px-4 pb-8 pt-3">
      <button
        type="button"
        onClick={() => navigate("/training")}
        className="pressable w-fit text-sm font-bold text-muted"
      >
        ← 训练
      </button>

      <p className="mt-3 text-[11px] font-bold uppercase tracking-widest text-muted">
        {stat?.muscle || "动作"}
      </p>
      <h1 className="font-display mt-1 text-[26px] font-bold tracking-tight">{name}</h1>
      <p className="mt-1 text-sm text-muted">
        上次 {fmtWeight(stat?.last_weight)}
        {stat?.last_reps != null ? ` × ${stat.last_reps}` : ""}
        <span className="mx-1.5 text-line">·</span>
        最好 {fmtWeight(stat?.best_weight)}
      </p>

      <section className="mt-4 rounded-2xl border border-line bg-elevated px-2 pb-2 pt-3">
        <p className="px-2 text-[11px] font-bold text-muted">重量走势</p>
        {isLoading ? (
          <p className="px-2 py-8 text-sm text-muted">加载中…</p>
        ) : chartPoints.length === 0 ? (
          <p className="px-2 py-8 text-sm text-muted">还没有带重量的记录。</p>
        ) : (
          <WeightTrendChart points={chartPoints} />
        )}
      </section>

      <section className="mt-5">
        <p className="text-[11px] font-bold uppercase tracking-widest text-muted">每次做组</p>
        {history.length === 0 ? (
          <p className="mt-3 text-sm text-muted">完成并勾选组次后会出现在这里。</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {history.map((p, i) => {
              const prev = history[i + 1];
              const delta =
                p.weight != null && prev?.weight != null
                  ? Math.round((p.weight - prev.weight) * 10) / 10
                  : null;
              return (
                <li
                  key={`${p.date}-${p.sessionId}`}
                  className="rounded-2xl border border-line bg-elevated px-3.5 py-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-num text-sm font-bold">{p.date}</p>
                      <p className="mt-0.5 text-[11px] text-muted">
                        {p.split || "训练"} · {p.setsDone} 组完成
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-num text-sm font-extrabold">
                        {fmtWeight(p.weight)}
                        {p.reps != null ? ` × ${p.reps}` : ""}
                      </p>
                      {delta != null && delta !== 0 && (
                        <p
                          className={`text-[11px] font-bold ${delta > 0 ? "text-ok" : "text-danger"}`}
                        >
                          {delta > 0 ? `较上场 +${delta}kg` : `较上场 ${delta}kg`}
                        </p>
                      )}
                      {delta === 0 && <p className="text-[11px] text-muted">较上场持平</p>}
                    </div>
                  </div>
                  {p.sets.length > 0 && (
                    <p className="mt-2 font-num text-[12px] leading-relaxed text-ink/80">
                      {p.sets
                        .map((s) => {
                          const w = s.weight != null ? `${s.weight}kg` : "自重";
                          const r = s.reps != null ? `×${s.reps}` : "";
                          return `${w}${r}`;
                        })
                        .join("  ·  ")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function decodeName(raw: string) {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function fmtWeight(w: number | null | undefined) {
  if (w == null) return "自重";
  return `${w}kg`;
}

type HistSet = { weight: number | null; reps: number | null };
type HistPoint = {
  sessionId: number;
  date: string;
  split: string | null;
  weight: number | null;
  reps: number | null;
  setsDone: number;
  sets: HistSet[];
};

function exerciseHistory(sessions: TrainingSession[], name: string): HistPoint[] {
  const rows: HistPoint[] = [];
  for (const s of sessions) {
    if (s.status !== "done" && s.status !== "active") continue;
    const sets = s.sets.filter((x) => x.exercise_name === name && x.completed);
    if (!sets.length) continue;
    const weight = bestWeight(sets);
    const bestSet =
      weight == null ? sets[0] : sets.find((x) => x.actual_weight === weight) || sets[0];
    rows.push({
      sessionId: s.id,
      date: s.session_date,
      split: s.split_label ?? null,
      weight,
      reps: bestSet.actual_reps ?? null,
      setsDone: sets.length,
      sets: sets.map((x) => ({
        weight: x.actual_weight ?? x.target_weight ?? null,
        reps: x.actual_reps ?? null,
      })),
    });
  }
  return rows.sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? 1 : -1;
    return b.sessionId - a.sessionId;
  });
}

function bestWeight(sets: SetLog[]): number | null {
  let best: number | null = null;
  for (const s of sets) {
    if (s.actual_weight == null) continue;
    if (best == null || s.actual_weight > best) best = s.actual_weight;
  }
  return best;
}
