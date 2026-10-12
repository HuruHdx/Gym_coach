import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { TrainingDashboard } from "../components/dashboard/TrainingDashboard";
import { MUSCLE_OPTIONS } from "../types";
import type { ExerciseStat, SetLog, TrainingDashboard as DashboardData, TrainingSession } from "../types";

type TabKey = "history" | "exercises";


const STATUS_LABEL: Record<string, string> = {
  active: "进行中",
  done: "已完成",
  abandoned: "已作废",
  draft: "草稿",
};

export function TrainingPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>("history");
  const [muscle, setMuscle] = useState<string>("全部");
  const [detailId, setDetailId] = useState<number | null>(null);
  const openExercise = (name: string) =>
    navigate(`/training/exercise/${encodeURIComponent(name)}`);

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=30"),
  });
  const { data: exercises = [] } = useQuery({
    queryKey: ["exercises"],
    queryFn: () => api<ExerciseStat[]>("/api/training/exercises"),
  });
  const { data: dashboard } = useQuery({
    queryKey: ["training-dashboard"],
    queryFn: () => api<DashboardData>("/api/training/dashboard"),
  });

  const filteredExercises = useMemo(() => {
    if (muscle === "全部") return exercises;
    return exercises.filter((ex) => (ex.muscle || "") === muscle);
  }, [exercises, muscle]);

  const detailSession = useMemo(
    () => sessions.find((s) => s.id === detailId) ?? null,
    [sessions, detailId],
  );

  const doneCount = sessions.filter((s) => s.status === "done").length;

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <p className="font-display text-[11px] font-extrabold uppercase tracking-[0.12em] text-muted">
        Gym Coach
      </p>
      <h1 className="font-display text-[26px] font-bold tracking-tight">训练</h1>
      <p className="mt-1 text-sm text-muted">
        {doneCount > 0 ? `已完成 ${doneCount} 场` : "完成训练后出现战报"}
      </p>

      {dashboard && (
        <div className="mt-4">
          <TrainingDashboard
            data={dashboard}
            onOpenSession={(id) => {
              setTab("history");
              setDetailId(id);
            }}
            onOpenExercise={openExercise}
          />
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-1 rounded-xl border border-line bg-elevated p-1">
        <SegBtn active={tab === "history"} onClick={() => setTab("history")} label="历史" />
        <SegBtn active={tab === "exercises"} onClick={() => setTab("exercises")} label="我的动作" />
      </div>

      {tab === "history" && (
        <section className="mt-4">
          {isLoading && <p className="text-sm text-muted">加载中…</p>}
          {!isLoading && sessions.length === 0 && (
            <div className="mt-2 flex min-h-[36vh] flex-col justify-end rounded-2xl border border-dashed border-line bg-elevated/60 p-5">
              <p className="font-display text-xl font-extrabold">还没有训练记录</p>
              <p className="mt-2 text-sm text-muted">去教练生成并采纳，今日勾完后会出现在这里。</p>
              <Link to="/coach" className="mt-4 text-sm font-bold underline">
                去教练 →
              </Link>
            </div>
          )}
          <ul className="space-y-2">
            {sessions.map((s) => {
              const names = [...new Set(s.sets.map((x) => x.exercise_name))];
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setDetailId(s.id)}
                    className="pressable w-full rounded-xl border border-line bg-elevated px-3.5 py-3 text-left transition hover:border-ink/30"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-display text-sm font-bold">
                        {s.session_date}
                        <span className="text-muted"> · </span>
                        {s.split_label || "训练"}
                      </div>
                      <span
                        className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${
                          s.status === "done"
                            ? "bg-ok/15 text-ok"
                            : s.status === "active"
                              ? "bg-accent/30 text-accent-ink"
                              : "bg-line text-muted"
                        }`}
                      >
                        {STATUS_LABEL[s.status] || s.status}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs text-muted">
                      {s.progress.done}/{s.progress.total} 组
                      {s.duration_minutes != null && s.duration_minutes >= 1
                        ? ` · ${s.duration_minutes} 分钟`
                        : ""}
                      {s.session_outcome ? ` · ${s.session_outcome}` : ""}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-ink/80">
                      {names.slice(0, 5).join("、")}
                      {names.length > 5 ? "…" : ""}
                    </p>
                    <p className="mt-2 text-[11px] font-bold text-muted">查看详情 →</p>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {tab === "exercises" && (
        <section className="mt-4">
          <p className="mb-2 text-xs text-muted">点动作看历次重量对比（上场 / 最好）。</p>
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto pb-1">
            {["全部", ...MUSCLE_OPTIONS].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMuscle(m)}
                className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-bold ${
                  muscle === m
                    ? "bg-accent text-accent-ink"
                    : "border border-line bg-elevated text-muted"
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          {filteredExercises.length === 0 ? (
            <p className="mt-4 text-sm text-muted">
              {exercises.length === 0
                ? "完成一次训练后，这里会出现上次/最好重量。"
                : `暂无「${muscle}」相关动作沉淀。`}
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-line rounded-xl border border-line bg-elevated">
              {filteredExercises.map((ex) => (
                <li key={ex.name}>
                  <button
                    type="button"
                    onClick={() => openExercise(ex.name)}
                    className="pressable flex w-full items-center justify-between gap-2 px-3.5 py-3 text-left"
                  >
                    <div className="min-w-0">
                      <div className="font-display text-sm font-bold">{ex.name}</div>
                      <div className="text-[11px] text-muted">{ex.muscle || "—"}</div>
                    </div>
                    <div className="shrink-0 text-right text-xs">
                      <div className="font-display font-bold">
                        上次{" "}
                        {ex.last_weight != null ? `${ex.last_weight}kg` : "自重"}
                        {ex.last_reps != null ? ` × ${ex.last_reps}` : ""}
                      </div>
                      <div className="mt-0.5 flex items-center justify-end gap-1 text-muted">
                        {(ex.last_feeling || ex.last_outcome) && (
                          <span className="rounded bg-line/60 px-1 py-0.5 text-[10px]">
                            {ex.last_feeling || ex.last_outcome}
                          </span>
                        )}
                        <span>
                          最好 {ex.best_weight != null ? `${ex.best_weight}kg` : "—"}
                          {ex.trend && ex.trend !== "→" ? ` ${ex.trend}` : ""}
                        </span>
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

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

function SegBtn({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg py-2.5 text-center text-xs font-extrabold transition ${
        active ? "bg-ink text-accent" : "text-muted"
      }`}
    >
      {label}
    </button>
  );
}

function SessionDetailSheet({
  session,
  sessions,
  onClose,
  onOpenExercise,
}: {
  session: TrainingSession;
  sessions: TrainingSession[];
  onClose: () => void;
  onOpenExercise: (name: string) => void;
}) {
  const groups = useMemo(() => groupSets(session.sets), [session.sets]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭" onClick={onClose} />
      <div className="relative z-10 flex max-h-[88dvh] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-line bg-bg shadow-xl sm:rounded-2xl">
        <div className="shrink-0 border-b border-line px-5 pb-3 pt-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-widest text-muted">
                {session.session_date}
              </p>
              <h2 className="font-display mt-1 text-xl font-extrabold">
                {session.split_label || "训练"}
              </h2>
            </div>
            <button
              type="button"
              className="rounded-md border border-line px-3 py-1.5 text-xs font-bold"
              onClick={onClose}
            >
              关闭
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
            <Chip
              label={STATUS_LABEL[session.status] || session.status}
              tone={session.status === "done" ? "ok" : "muted"}
            />
            <Chip label={`${session.progress.done}/${session.progress.total} 组`} />
            {session.duration_minutes != null && session.duration_minutes >= 1 && (
              <Chip label={`${session.duration_minutes} 分钟`} />
            )}
            {session.session_outcome && <Chip label={session.session_outcome} />}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted">
            动作组次 ({groups.length})
          </p>
          <div className="mt-2 space-y-3">
            {groups.map((g) => {
              const thisBest = bestWeightInSets(g.sets);
              const prior = priorSessionBest(sessions, session, g.name);
              const delta =
                thisBest != null && prior != null
                  ? Math.round((thisBest - prior) * 10) / 10
                  : null;
              return (
                <div key={g.name} className="rounded-xl border border-line bg-elevated px-3 py-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => onOpenExercise(g.name)}
                      className="text-left"
                    >
                      <div className="font-display text-sm font-bold underline-offset-2 hover:underline">
                        {g.name}
                        {g.muscle && (
                          <span className="ml-1.5 text-[10px] font-bold text-muted no-underline">
                            {g.muscle}
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-[11px] text-muted">
                        本场最高 {fmtWeight(thisBest)}
                        {prior != null ? ` · 上场 ${fmtWeight(prior)}` : ""}
                        {delta != null && delta !== 0
                          ? delta > 0
                            ? ` · ↑${delta}kg`
                            : ` · ↓${Math.abs(delta)}kg`
                          : prior != null && thisBest != null
                            ? " · 持平"
                            : ""}
                      </p>
                    </button>
                    <span className="shrink-0 text-[11px] text-muted">
                      {g.sets.filter((s) => s.completed).length}/{g.sets.length} 组
                    </span>
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {g.sets.map((s) => {
                      const w = s.actual_weight ?? s.target_weight;
                      const r = s.actual_reps ?? s.target_reps;
                      return (
                        <li
                          key={s.id}
                          className={`text-xs ${s.completed ? "text-ink" : "text-muted"}`}
                        >
                          第{s.set_index}组 · {w != null ? `${w}kg` : "自重"}
                          {r != null ? ` × ${r}` : ""}
                          {s.feeling ? ` · ${s.feeling}` : ""}
                          {!s.completed ? " · 未完成" : ""}
                        </li>
                      );
                    })}
                  </ul>
                  {g.sets.some((s) => s.note) && (
                    <div className="mt-2 space-y-1 border-t border-line/60 pt-2">
                      {g.sets
                        .filter((s) => s.note)
                        .map((s) => (
                          <p key={s.id} className="text-[11px] text-muted">
                            组{s.set_index}备注：{s.note}
                          </p>
                        ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {session.summary && (
            <div className="mt-5">
              <p className="text-[11px] font-bold uppercase tracking-widest text-muted">
                教练总结
              </p>
              <div className="mt-2 whitespace-pre-wrap rounded-xl border border-line bg-elevated px-3.5 py-3 text-sm leading-relaxed text-ink">
                {session.summary}
              </div>
            </div>
          )}

          {!session.summary && session.status === "done" && (
            <p className="mt-5 text-xs text-muted">这场没有留下文字总结。</p>
          )}
        </div>

        <div className="shrink-0 border-t border-line px-5 py-3">
          {session.status === "active" ? (
            <Link
              to="/"
              onClick={onClose}
              className="pressable block w-full rounded-md bg-accent py-3 text-center font-display text-sm font-extrabold text-accent-ink"
            >
              回到今日继续打卡 →
            </Link>
          ) : session.status === "done" && isToday(session.session_date) ? (
            <Link
              to="/recap"
              onClick={onClose}
              className="pressable block w-full rounded-md border border-line py-3 text-center text-sm font-bold"
            >
              打开今日结算海报 →
            </Link>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="pressable w-full rounded-md border border-line py-3 text-sm font-bold"
            >
              关闭
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Chip({
  label,
  tone = "muted",
}: {
  label: string;
  tone?: "muted" | "ok";
}) {
  return (
    <span
      className={`rounded-md px-2 py-1 font-bold ${
        tone === "ok" ? "bg-ok/15 text-ok" : "border border-line bg-elevated text-muted"
      }`}
    >
      {label}
    </span>
  );
}

function groupSets(sets: SetLog[]) {
  const map = new Map<string, { name: string; muscle?: string | null; sets: SetLog[] }>();
  for (const s of sets) {
    const cur = map.get(s.exercise_name);
    if (cur) cur.sets.push(s);
    else map.set(s.exercise_name, { name: s.exercise_name, muscle: s.muscle, sets: [s] });
  }
  return [...map.values()];
}

function bestWeightInSets(sets: SetLog[]): number | null {
  let best: number | null = null;
  for (const s of sets) {
    if (!s.completed || s.actual_weight == null) continue;
    if (best == null || s.actual_weight > best) best = s.actual_weight;
  }
  return best;
}

/** 比当前场更早、做过同动作的最近一场最高重量 */
function priorSessionBest(
  sessions: TrainingSession[],
  current: TrainingSession,
  exerciseName: string,
): number | null {
  const older = sessions
    .filter(
      (s) =>
        s.id !== current.id &&
        s.status === "done" &&
        (s.session_date < current.session_date ||
          (s.session_date === current.session_date && s.id < current.id)),
    )
    .sort((a, b) => {
      if (a.session_date !== b.session_date) return a.session_date < b.session_date ? 1 : -1;
      return b.id - a.id;
    });
  for (const s of older) {
    const sets = s.sets.filter((x) => x.exercise_name === exerciseName);
    const w = bestWeightInSets(sets);
    if (w != null) return w;
  }
  return null;
}

function fmtWeight(w: number | null | undefined) {
  if (w == null) return "自重";
  return `${w}kg`;
}

function isToday(sessionDate: string) {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return sessionDate === `${y}-${m}-${day}`;
}
