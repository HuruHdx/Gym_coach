import type { TrainingSession } from "../../types";

export type Trend = "up" | "down" | "flat" | "new";

export function sessionTitle(session: TrainingSession): string {
  const when = session.session_date.slice(5);
  const split = (session.split_label || "").replace(/训$/, "").trim();
  return `${split || primaryMuscle(session)} · ${when}`;
}

export function sessionFacts(session: TrainingSession): string {
  const done = session.sets.filter((set) => set.completed);
  const moves = new Set(done.map((set) => set.exercise_name)).size;
  const parts: string[] = [];
  if (moves > 0) parts.push(`${moves} 个动作`);
  parts.push(`${session.progress.done} 组`);
  if (session.duration_minutes != null && session.duration_minutes >= 1) {
    parts.push(`${session.duration_minutes} 分钟`);
  }
  return parts.join(" · ");
}

type Best = { weight: number | null; reps: number | null };

function bestOf(session: TrainingSession, name: string): Best {
  let weight: number | null = null;
  let reps: number | null = null;
  for (const set of session.sets) {
    if (!set.completed || set.exercise_name !== name) continue;
    if (set.actual_weight != null && set.actual_weight > 0) {
      if (weight == null || set.actual_weight > weight) {
        weight = set.actual_weight;
        reps = set.actual_reps ?? null;
      }
    } else if (weight == null && set.actual_reps != null && (reps == null || set.actual_reps > reps)) {
      reps = set.actual_reps;
    }
  }
  return { weight, reps };
}

function earlierDone(sessions: TrainingSession[], current: TrainingSession): TrainingSession[] {
  return sessions
    .filter(
      (item) =>
        item.id !== current.id &&
        item.status === "done" &&
        isEarlier(item, current),
    )
    .sort((a, b) => (isEarlier(a, b) ? 1 : -1));
}

/** 这场相对以往的结果：破纪录、加重、加重次数。没有可比变化时返回空。 */
export function sessionResultLine(session: TrainingSession, sessions: TrainingSession[]): string {
  const names = [...new Set(session.sets.filter((set) => set.completed).map((set) => set.exercise_name))];
  const older = earlierDone(sessions, session);
  const prs: string[] = [];
  const ups: string[] = [];
  for (const name of names) {
    const cur = bestOf(session, name);
    let histWeight: number | null = null;
    let prev: Best | null = null;
    for (const item of older) {
      const best = bestOf(item, name);
      if (best.weight == null && best.reps == null) continue;
      if (!prev) prev = best;
      if (best.weight != null && (histWeight == null || best.weight > histWeight)) histWeight = best.weight;
    }
    if (cur.weight != null && histWeight != null && cur.weight > histWeight) {
      prs.push(`${name}破纪录`);
      continue;
    }
    if (cur.weight != null && prev?.weight != null && cur.weight > prev.weight) {
      const delta = Math.round((cur.weight - prev.weight) * 10) / 10;
      ups.push(`${name} +${delta}kg`);
      continue;
    }
    if (cur.weight == null && cur.reps != null && prev?.reps != null && cur.reps > prev.reps) {
      ups.push(`${name} +${cur.reps - prev.reps}次`);
    }
  }
  return [...prs, ...ups].slice(0, 2).join(" · ");
}

export function primaryMuscle(session: TrainingSession): string {
  const counts = new Map<string, number>();
  for (const set of session.sets) {
    if (!set.completed) continue;
    const muscle = (set.muscle || "").trim();
    if (!muscle || muscle === "全身") continue;
    counts.set(muscle, (counts.get(muscle) || 0) + 1);
  }
  let best = "";
  let bestCount = 0;
  for (const [muscle, count] of counts) {
    if (count > bestCount) {
      best = muscle;
      bestCount = count;
    }
  }
  if (best) return best;
  const label = (session.split_label || "").replace(/训$/, "");
  return label || "训练";
}

function isEarlier(a: TrainingSession, b: TrainingSession): boolean {
  if (a.session_date !== b.session_date) return a.session_date < b.session_date;
  return a.id < b.id;
}

/** 同一部位上一场的容量对比。没容量可比时不算涨跌。 */
export function volumeTrend(current: TrainingSession, sessions: TrainingSession[]): Trend {
  const muscle = primaryMuscle(current);
  const prev = sessions
    .filter(
      (item) =>
        item.id !== current.id &&
        item.status === "done" &&
        primaryMuscle(item) === muscle &&
        isEarlier(item, current),
    )
    .sort((a, b) => (isEarlier(a, b) ? 1 : -1))[0];
  if (!prev) return "new";
  const currVol = current.total_volume ?? 0;
  const prevVol = prev.total_volume ?? 0;
  if (currVol <= 0 || prevVol <= 0) return "flat";
  const ratio = (currVol - prevVol) / prevVol;
  if (ratio >= 0.03) return "up";
  if (ratio <= -0.03) return "down";
  return "flat";
}
