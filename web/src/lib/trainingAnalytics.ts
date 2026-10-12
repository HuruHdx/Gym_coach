import type { ExerciseStat, TrainingSession } from "../types";

const WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"] as const;

export type WeekDayCell = {
  date: string; // YYYY-MM-DD
  label: string; // 一…日
  isToday: boolean;
  trained: boolean;
  muscles: string[];
  sessionId?: number;
  split?: string | null;
};

export type WeekTrainingSummary = {
  days: WeekDayCell[];
  trainedDays: number;
  targetDays: number;
  muscles: string[];
  sessions: number;
};

export type PrHit = {
  kind: "session" | "exercise";
  title: string;
  subtitle: string;
  date?: string;
  sessionId?: number;
  exerciseName?: string;
};

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

export function toDateKey(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** 本周一 00:00（本地） */
export function startOfWeekMonday(now = new Date()): Date {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function musclesFromSession(s: TrainingSession): string[] {
  const out: string[] = [];
  for (const set of s.sets) {
    const m = set.muscle?.trim();
    if (m && m !== "全身" && !out.includes(m)) out.push(m);
  }
  if (!out.length && s.split_label) {
    const label = s.split_label.replace(/训$/, "");
    for (const m of ["胸", "背", "肩", "腿", "臂", "核心"]) {
      if (label.includes(m) && !out.includes(m)) out.push(m);
    }
  }
  return out;
}

export function buildWeekTraining(
  sessions: TrainingSession[],
  targetDays: number,
  now = new Date(),
): WeekTrainingSummary {
  const start = startOfWeekMonday(now);
  const todayKey = toDateKey(now);
  const done = sessions.filter((s) => s.status === "done" || s.status === "active");

  const byDate = new Map<string, TrainingSession[]>();
  for (const s of done) {
    const list = byDate.get(s.session_date) || [];
    list.push(s);
    byDate.set(s.session_date, list);
  }

  const days: WeekDayCell[] = [];
  const allMuscles: string[] = [];
  let trainedDays = 0;
  let sessionCount = 0;

  for (let i = 0; i < 7; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const key = toDateKey(d);
    const daySessions = byDate.get(key) || [];
    const muscles = [...new Set(daySessions.flatMap(musclesFromSession))];
    const trained = daySessions.length > 0;
    if (trained) {
      trainedDays += 1;
      sessionCount += daySessions.length;
      for (const m of muscles) {
        if (!allMuscles.includes(m)) allMuscles.push(m);
      }
    }
    const primary = daySessions[0];
    days.push({
      date: key,
      label: WEEKDAY_LABELS[i],
      isToday: key === todayKey,
      trained,
      muscles,
      sessionId: primary?.id,
      split: primary?.split_label,
    });
  }

  return {
    days,
    trainedDays,
    targetDays: Math.min(7, Math.max(1, targetDays || 4)),
    muscles: allMuscles,
    sessions: sessionCount,
  };
}

/** 近期突破：有「有突破」的场次 + 趋势上涨的动作 */
export function buildPrHits(
  sessions: TrainingSession[],
  exercises: ExerciseStat[],
  limit = 5,
): PrHit[] {
  const hits: PrHit[] = [];

  const breakthroughSessions = sessions
    .filter((s) => s.status === "done" && s.session_outcome === "有突破")
    .slice(0, 8);

  for (const s of breakthroughSessions) {
    const names = [...new Set(s.sets.filter((x) => x.completed).map((x) => x.exercise_name))].slice(
      0,
      3,
    );
    hits.push({
      kind: "session",
      title: `${s.split_label || "训练"} · 有突破`,
      subtitle: names.length ? names.join("、") : "本场多项加重完成",
      date: s.session_date,
      sessionId: s.id,
    });
  }

  const rising = exercises
    .filter((e) => e.trend === "↑" && e.last_weight != null)
    .sort((a, b) => (b.last_weight ?? 0) - (a.last_weight ?? 0));

  for (const e of rising) {
    const best = e.best_weight != null ? `${e.best_weight}kg` : "—";
    const last = e.last_weight != null ? `${e.last_weight}kg` : "自重";
    hits.push({
      kind: "exercise",
      title: e.name,
      subtitle: `上次 ${last}${e.last_reps != null ? ` × ${e.last_reps}` : ""} · 最好 ${best}`,
      exerciseName: e.name,
    });
  }

  // 去重：同动作优先保留 exercise 条；同场次不重复
  const seen = new Set<string>();
  const out: PrHit[] = [];
  for (const h of hits) {
    const key =
      h.kind === "session" ? `s:${h.sessionId}` : `e:${h.exerciseName}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(h);
    if (out.length >= limit) break;
  }
  return out;
}
