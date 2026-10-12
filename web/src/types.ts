export const MUSCLE_OPTIONS = ["胸", "背", "肩", "腿", "臂", "核心", "全身"] as const;
export type Goal = "增肌" | "减脂" | "力量" | "塑形";
export type Experience = "新手" | "进阶" | "老炮";

export type Profile = {
  id: number;
  goal: Goal;
  experience: Experience;
  weight_kg: number;
  height_cm: number | null;
  days_per_week: number;
  session_minutes: number;
  injuries: string[];
  preferences: string[];
  avoid_foods: string[];
  protein_target_g: number | null;
  calorie_target: number | null;
};

export type CardItem = {
  id: string;
  title: string;
  subtitle?: string | null;
  meta: Record<string, unknown>;
  selected: boolean;
};

export type CardBlock = {
  kind: "card";
  card_type: string;
  title: string;
  status: string;
  items: CardItem[];
  actions: string[];
  meta: Record<string, unknown>;
};

export type Block =
  | { kind: "text"; text: string }
  | CardBlock;

export type Suggestion = {
  label: string;
  prompt: string;
};

export type AgentReply = {
  blocks: Block[];
  suggestions?: Suggestion[];
  trace_id?: number | null;
};

export type SetLog = {
  id: number;
  session_id: number;
  exercise_name: string;
  muscle?: string | null;
  set_index: number;
  target_reps?: string | null;
  target_weight?: number | null;
  actual_weight?: number | null;
  actual_reps?: number | null;
  completed: boolean;
  feeling?: string | null;
  note?: string | null;
};

export type TrainingSession = {
  id: number;
  session_date: string;
  split_label?: string | null;
  source: string;
  status: string;
  note?: string | null;
  total_volume?: number | null;
  session_outcome?: string | null;
  summary?: string | null;
  duration_seconds?: number;
  timer_started_at?: string | null;
  duration_minutes?: number | null;
  sets: SetLog[];
  progress: { done: number; total: number };
};

export type ExerciseStat = {
  name: string;
  muscle?: string | null;
  last_weight?: number | null;
  last_reps?: number | null;
  last_feeling?: string | null;
  last_outcome?: string | null;
  best_weight?: number | null;
  trend: string;
};

export type WeekDayCell = {
  date: string;
  label: string;
  is_today: boolean;
  trained: boolean;
  muscles: string[];
  session_id?: number | null;
  split?: string | null;
  duration_minutes?: number | null;
  completion_pct?: number | null;
};

export type WeekRhythm = {
  days: WeekDayCell[];
  trained_days: number;
  target_days: number;
  sessions: number;
};

export type MusclePulse = {
  muscle: string;
  days_since?: number | null;
  count_30d: number;
  last_date?: string | null;
  last_session_id?: number | null;
  trend: string;
  status: string;
};

export type LiftDelta = {
  exercise_name: string;
  load: string;
  weight?: number | null;
  reps?: number | null;
  prev_load?: string | null;
  delta_kind: string;
  delta_label: string;
  weight_delta?: number | null;
  reps_delta?: number | null;
};

export type SessionCompare = {
  session_id: number;
  session_date: string;
  split_label?: string | null;
  muscle?: string | null;
  duration_minutes?: number | null;
  done_sets: number;
  total_sets: number;
  quality: string;
  prev_session_id?: number | null;
  prev_date?: string | null;
  lifts: LiftDelta[];
};

export type KeyLift = {
  exercise_name: string;
  muscle?: string | null;
  load: string;
  weight?: number | null;
  reps?: number | null;
  delta_kg: number;
  delta_label: string;
  trend: string;
  is_pr: boolean;
  last_date?: string | null;
};

export type TrainingDashboard = {
  as_of: string;
  headline: string;
  week: WeekRhythm;
  muscle_pulse: MusclePulse[];
  session_compare?: SessionCompare | null;
  key_lifts: KeyLift[];
};

export type ExerciseOption = {
  name: string;
  muscle: string;
  category: string;
  tips?: string | null;
};

export type AlternativesResponse = {
  muscle: string;
  options: string[];
  items: ExerciseOption[];
  banned_injuries: string[];
};

export function rebuildSubtitle(meta: Record<string, unknown>): string {
  const sets = meta.sets;
  const reps = (meta.reps as string) || "-";
  const weight = meta.weight;
  const parts: string[] = [];
  if (sets != null) parts.push(`${sets}×${reps}`);
  else parts.push(String(reps));
  if (weight != null) parts.push(`建议 ${weight}kg`);
  return parts.join(" · ");
}
