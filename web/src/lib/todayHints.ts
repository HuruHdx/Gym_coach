import type { MusclePulse, TrainingSession } from "../types";

const BIG = new Set(["胸", "背", "腿"]);
const SMALL = new Set(["肩", "臂"]);
/** 核心/腹可每天练，阈值 0 = 始终 ready */
const DAILY = new Set(["核心", "腹"]);

export function thresholdDays(muscle: string): number {
  if (DAILY.has(muscle)) return 0;
  if (BIG.has(muscle)) return 3;
  if (SMALL.has(muscle)) return 2;
  return 3;
}

export type BlockRecoveryHint = {
  ready: boolean;
  text: string;
  muscles: string[];
};

/** 下一板块主肌群是否够间隔；不够则给软提示（不锁死）。 */
export function buildBlockRecoveryHint(
  muscles: string[] | undefined | null,
  pulse: MusclePulse[] | undefined | null,
): BlockRecoveryHint | null {
  const list = (muscles || []).map((m) => m.trim()).filter(Boolean);
  if (list.length === 0) return null;
  const byMuscle = new Map(
    (pulse || [])
      .filter((p) => p.days_since != null && Number.isFinite(p.days_since))
      .map((p) => [p.muscle, p.days_since as number]),
  );
  const notReady: { muscle: string; days: number; need: number }[] = [];
  for (const m of list) {
    const need = thresholdDays(m);
    if (need <= 0) continue;
    const days = byMuscle.get(m);
    if (days == null) continue; // 无历史 → 视为可练
    if (days < need) notReady.push({ muscle: m, days, need });
  }
  if (notReady.length === 0) {
    return { ready: true, text: "", muscles: list };
  }
  notReady.sort((a, b) => a.days - b.days);
  const top = notReady[0];
  return {
    ready: false,
    text: `${top.muscle}距上次仅 ${top.days} 天（建议间隔 ${top.need} 天），可休息或换板块`,
    muscles: notReady.map((r) => r.muscle),
  };
}

export type MuscleGapView = {
  headline: string;
  detail: string;
  rows: { muscle: string; days: number; ready: boolean }[];
};

/** 用 dashboard.muscle_pulse 近似 muscle-gap；无历史返回 null。 */
export function buildMuscleGap(pulse: MusclePulse[] | undefined | null): MuscleGapView | null {
  const rows = (pulse || [])
    .filter((p) => p.days_since != null && Number.isFinite(p.days_since))
    .map((p) => ({
      muscle: p.muscle,
      days: p.days_since as number,
      ready: (p.days_since as number) >= thresholdDays(p.muscle),
    }))
    .sort((a, b) => b.days - a.days);
  if (rows.length === 0) return null;

  const ready = rows.filter((r) => r.ready);
  const top = ready[0] ?? rows[0];
  const headline = ready[0]
    ? `今天建议练${top.muscle} · 距上次 ${top.days} 天`
    : `隔得最久的是${top.muscle}，已经 ${top.days} 天`;
  const detail = rows
    .slice(0, 4)
    .map((r) => `${r.muscle} ${r.days} 天`)
    .join(" · ");
  return { headline, detail, rows };
}

export type RestHint = { text: string };

/** §2.12 越界提示：只在真触发时返回。 */
export function buildRestHints(
  sessions: TrainingSession[],
  opts: { targetDays: number; trainedDays: number },
): RestHint[] {
  const hints: RestHint[] = [];
  const done = sessions
    .filter((s) => s.status === "done")
    .slice()
    .sort((a, b) => b.session_date.localeCompare(a.session_date));

  // 同部位连练 ≥2 天
  const byDate = new Map<string, Set<string>>();
  for (const s of done) {
    if (s.source === "rest") continue;
    const muscles = new Set(
      s.sets
        .filter((set) => set.completed && !set.is_warmup && set.muscle)
        .map((set) => set.muscle as string),
    );
    if (muscles.size === 0) continue;
    const bag = byDate.get(s.session_date) || new Set<string>();
    muscles.forEach((m) => bag.add(m));
    byDate.set(s.session_date, bag);
  }
  const dates = [...byDate.keys()].sort().reverse();
  if (dates.length >= 2) {
    const a = byDate.get(dates[0])!;
    const b = byDate.get(dates[1])!;
    const dayGap = daysBetween(dates[1], dates[0]);
    if (dayGap === 1) {
      for (const m of a) {
        if (b.has(m) && BIG.has(m)) {
          hints.push({ text: `${m}连着练了 2 天，明天换个部位或休息` });
          break;
        }
      }
    }
  }

  if (opts.trainedDays >= opts.targetDays && opts.targetDays > 0) {
    hints.push({ text: "这周够了，歇一天也行" });
  }

  // 连续无休 ≥6
  let streak = 0;
  const today = new Date();
  for (let i = 0; i < 14; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = isoDate(d);
    const daySessions = done.filter((s) => s.session_date === key);
    if (daySessions.some((s) => s.source === "rest")) break;
    if (daySessions.some((s) => s.source !== "rest")) {
      streak += 1;
    } else if (i > 0) {
      break;
    }
  }
  if (streak >= 6) {
    hints.push({ text: `连着练了 ${streak} 天，今天建议休息` });
  }

  // 去重
  const seen = new Set<string>();
  return hints.filter((h) => {
    if (seen.has(h.text)) return false;
    seen.add(h.text);
    return true;
  });
}

export function lastCompletedReps(
  sessions: TrainingSession[],
  exerciseName: string,
  excludeSessionId?: number | null,
): number | null {
  for (const session of sessions) {
    if (session.id === excludeSessionId) continue;
    if (session.status !== "done" || session.source === "rest") continue;
    const sets = session.sets
      .filter(
        (s) =>
          s.exercise_name === exerciseName &&
          s.completed &&
          !s.is_warmup &&
          s.actual_reps != null,
      )
      .sort((a, b) => b.set_index - a.set_index);
    if (sets[0]?.actual_reps != null) return sets[0].actual_reps;
  }
  return null;
}

/** 同动作 + 同组号的最近 actual_reps。 */
export function lastRepsForSet(
  sessions: TrainingSession[],
  exerciseName: string,
  setIndex: number,
  excludeSessionId?: number | null,
): number | null {
  for (const session of sessions) {
    if (session.id === excludeSessionId) continue;
    if (session.status !== "done" || session.source === "rest") continue;
    const hit = session.sets.find(
      (s) =>
        s.exercise_name === exerciseName &&
        s.set_index === setIndex &&
        s.completed &&
        !s.is_warmup &&
        s.actual_reps != null,
    );
    if (hit?.actual_reps != null) return hit.actual_reps;
  }
  return null;
}

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function daysBetween(earlier: string, later: string): number {
  const a = Date.parse(earlier);
  const b = Date.parse(later);
  if (Number.isNaN(a) || Number.isNaN(b)) return 99;
  return Math.round((b - a) / 86400000);
}
