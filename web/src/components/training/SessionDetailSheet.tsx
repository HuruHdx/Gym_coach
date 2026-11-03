import { useMemo } from "react";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import type { SetLog, TrainingSession } from "../../types";

const STATUS_LABEL: Record<string, string> = {
  active: "进行中",
  done: "已完成",
  abandoned: "已作废",
  draft: "草稿",
};

export function SessionDetailSheet({
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
              className="pressable grid h-8 w-8 place-items-center rounded-md border border-line text-ink"
              aria-label="关闭"
              onClick={onClose}
            >
              <X size={18} />
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
            {groups.map((group) => {
              const thisBest = bestWeightInSets(group.sets);
              const prior = priorSessionBest(sessions, session, group.name);
              const delta =
                thisBest != null && prior != null ? Math.round((thisBest - prior) * 10) / 10 : null;
              return (
                <div key={group.name} className="rounded-xl border border-line bg-elevated px-3 py-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <button type="button" onClick={() => onOpenExercise(group.name)} className="text-left">
                      <div className="font-display text-sm font-bold">
                        {group.name}
                        {group.muscle && (
                          <span className="ml-1.5 text-[10px] font-bold text-muted">{group.muscle}</span>
                        )}
                      </div>
                      <p className="mt-0.5 text-[11px] text-muted">
                        本场最高 {fmtWeight(thisBest)}
                        {prior != null ? ` · 上场 ${fmtWeight(prior)}` : ""}
                        {delta != null && delta !== 0
                          ? delta > 0
                            ? ` · +${delta}kg`
                            : ` · ${delta}kg`
                          : prior != null && thisBest != null
                            ? " · 持平"
                            : ""}
                      </p>
                    </button>
                    <span className="shrink-0 text-[11px] text-muted">
                      {group.sets.filter((set) => set.completed).length}/{group.sets.length} 组
                    </span>
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {group.sets.map((set) => {
                      const weight = set.actual_weight ?? set.target_weight;
                      const reps = set.actual_reps ?? set.target_reps;
                      return (
                        <li key={set.id} className={`text-xs ${set.completed ? "text-ink" : "text-muted"}`}>
                          第{set.set_index}组 · {weight != null ? `${weight}kg` : "自重"}
                          {reps != null ? ` × ${reps}` : ""}
                          {set.feeling ? ` · ${set.feeling}` : ""}
                          {!set.completed ? " · 未完成" : ""}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </div>
          {session.summary && (
            <div className="mt-5">
              <p className="text-[11px] font-bold uppercase tracking-widest text-muted">教练总结</p>
              <div className="mt-2 whitespace-pre-wrap rounded-xl border border-line bg-elevated px-3.5 py-3 text-sm leading-relaxed text-ink">
                {session.summary}
              </div>
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-line px-5 py-3">
          {session.status === "active" ? (
            <Link
              to="/"
              onClick={onClose}
              className="pressable block w-full rounded-md bg-accent py-3 text-center font-display text-sm font-extrabold text-accent-ink"
            >
              回到今日继续打卡
            </Link>
          ) : session.status === "done" && isToday(session.session_date) ? (
            <Link
              to="/recap"
              onClick={onClose}
              className="pressable block w-full rounded-md border border-line py-3 text-center text-sm font-bold"
            >
              打开今日结算海报
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

function Chip({ label, tone = "muted" }: { label: string; tone?: "muted" | "ok" }) {
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
  for (const set of sets) {
    const current = map.get(set.exercise_name);
    if (current) current.sets.push(set);
    else map.set(set.exercise_name, { name: set.exercise_name, muscle: set.muscle, sets: [set] });
  }
  return [...map.values()];
}

function bestWeightInSets(sets: SetLog[]): number | null {
  let best: number | null = null;
  for (const set of sets) {
    if (!set.completed || set.actual_weight == null) continue;
    if (best == null || set.actual_weight > best) best = set.actual_weight;
  }
  return best;
}

function priorSessionBest(
  sessions: TrainingSession[],
  current: TrainingSession,
  exerciseName: string,
): number | null {
  const older = sessions
    .filter(
      (item) =>
        item.id !== current.id &&
        item.status === "done" &&
        (item.session_date < current.session_date ||
          (item.session_date === current.session_date && item.id < current.id)),
    )
    .sort((a, b) => {
      if (a.session_date !== b.session_date) return a.session_date < b.session_date ? 1 : -1;
      return b.id - a.id;
    });
  for (const item of older) {
    const weight = bestWeightInSets(item.sets.filter((set) => set.exercise_name === exerciseName));
    if (weight != null) return weight;
  }
  return null;
}

function fmtWeight(weight: number | null | undefined) {
  if (weight == null) return "自重";
  return `${weight}kg`;
}

function isToday(sessionDate: string) {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return sessionDate === `${now.getFullYear()}-${month}-${day}`;
}
