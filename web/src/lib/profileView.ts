import type { Profile, TrainingSession } from "../types";
import { startOfWeekMonday, toDateKey } from "./trainingAnalytics";

/** @deprecated 已改为 /api/auth/me 的 display_name；保留仅防旧引用编译。 */
export const DISPLAY_NAME = "小燃";

export type AuthUser = {
  id: number;
  phone: string;
  display_name: string | null;
};

/** 未自填昵称时的默认称呼：好听、好记，按账号稳定映射，不跟手机号拼数字。 */
const DEFAULT_NICKS = [
  "小燃",
  "阿练",
  "清清",
  "小满",
  "阿泽",
  "南风",
  "小禾",
  "阿川",
  "晚晴",
  "小屿",
  "阿野",
  "青柠",
  "小舟",
  "阿白",
  "初夏",
  "小棠",
  "阿辰",
  "拾光",
  "小鹿",
  "阿恒",
  "星野",
  "小安",
  "阿予",
  "林间",
] as const;

function stableNickIndex(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return h % DEFAULT_NICKS.length;
}

/** 展示名：自填昵称优先，否则按账号取一个好听的默认称呼。 */
export function displayNameOf(user: AuthUser | null | undefined): string {
  const nick = user?.display_name?.trim();
  if (nick) return nick;
  const seed = user?.id != null ? `id:${user.id}` : user?.phone ? `ph:${user.phone}` : "guest";
  return DEFAULT_NICKS[stableNickIndex(seed)] ?? "小燃";
}

// 选项目录统一在 profileOptions.ts。这里只做转发，避免两处各写一份后分叉。
export {
  DAY_OPTIONS,
  EXPERIENCE_OPTIONS,
  GOAL_OPTIONS,
  SESSION_MINUTE_OPTIONS,
  SCENES,
  preferencesForScene,
  sceneFromPreferences,
  type SceneId,
} from "./profileOptions";

/** 编辑页的时长快捷档位。包含引导页的 SESSION_MINUTE_OPTIONS，外加旧的 45 兼容已存值。 */
export const MINUTE_PRESETS = [40, 45, 60, 75, 90] as const;

/** 展示短名。存库用教练关键词能命中的写法：膝→膝盖，腕→手腕。 */
export const AVOID_PARTS = [
  { label: "肩", stored: "肩" },
  { label: "腰", stored: "腰" },
  { label: "膝", stored: "膝盖" },
  { label: "腕", stored: "手腕" },
  { label: "肘", stored: "肘" },
] as const;

const EXACT_PARTS = new Set<string>(AVOID_PARTS.flatMap((part) => [part.stored, part.label]));

export function partSelected(injuries: string[], stored: string, label: string): boolean {
  return injuries.some((tag) => tag === stored || tag === label || tag.includes(label));
}

export function injuryNote(injuries: string[]): string {
  return injuries.filter((tag) => tag && !EXACT_PARTS.has(tag)).join("、");
}

export function injuriesToSave(selectedStored: string[], note: string): string[] {
  const out = [...selectedStored];
  const extra = note.trim();
  if (extra && !out.includes(extra)) out.push(extra);
  return out;
}

export function selectedPartLabels(injuries: string[]): string[] {
  return AVOID_PARTS.filter((part) => partSelected(injuries, part.stored, part.label)).map(
    (part) => part.label,
  );
}

export function formatKg(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const rounded = Math.round(n * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function daysSince(iso: string, now = new Date()): number {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return 0;
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const that = Date.UTC(then.getFullYear(), then.getMonth(), then.getDate());
  return Math.max(0, Math.round((today - that) / 86400000));
}

/** 没有单独的体重恢复期字段。定稿文案是「3 天前」，未满 3 天不催记。 */
export const WEIGHT_NUDGE_DAYS = 3;

const LIFT_KEYS = ["卧推", "深蹲", "硬拉", "推举", "划船", "引体", "弯举", "臂屈伸"];

export function shortLift(name: string): string {
  for (const key of LIFT_KEYS) {
    if (name.includes(key)) return key;
  }
  return name.length > 4 ? name.slice(0, 4) : name;
}

export function weekDoneCount(sessions: TrainingSession[], now = new Date()): number {
  const start = toDateKey(startOfWeekMonday(now));
  return sessions.filter((session) => session.status === "done" && session.session_date >= start).length;
}

export type LiftMove = { name: string; from: number; to: number };

/** 本周完成组里，相对本周前最后一次，涨幅最大的主项。只陈述重量，不判断练得够不够。 */
export function biggestWeekLift(sessions: TrainingSession[], now = new Date()): LiftMove | null {
  const startKey = toDateKey(startOfWeekMonday(now));
  const done = [...sessions]
    .filter((session) => session.status === "done")
    .sort((a, b) =>
      a.session_date < b.session_date ? -1 : a.session_date > b.session_date ? 1 : a.id - b.id,
    );

  const series = new Map<string, { date: string; weight: number }[]>();
  for (const session of done) {
    const best = new Map<string, number>();
    for (const set of session.sets) {
      if (!set.completed) continue;
      const weight = set.actual_weight ?? set.target_weight;
      if (weight == null || weight <= 0) continue;
      best.set(set.exercise_name, Math.max(best.get(set.exercise_name) ?? 0, weight));
    }
    for (const [name, weight] of best) {
      const list = series.get(name) ?? [];
      list.push({ date: session.session_date, weight });
      series.set(name, list);
    }
  }

  let best: (LiftMove & { delta: number }) | null = null;
  for (const [name, points] of series) {
    const inWeek = points.filter((point) => point.date >= startKey);
    if (!inWeek.length) continue;
    const to = inWeek[inWeek.length - 1].weight;
    const before = points.filter((point) => point.date < startKey);
    const from = before.length ? before[before.length - 1].weight : inWeek[0].weight;
    const delta = Math.round((to - from) * 10) / 10;
    if (delta <= 0) continue;
    if (!best || delta > best.delta) best = { name, from, to, delta };
  }
  return best ? { name: best.name, from: best.from, to: best.to } : null;
}

export function insightHeadline(sessions: TrainingSession[], weekCount: number): string {
  const move = biggestWeekLift(sessions);
  if (move) return `本周${shortLift(move.name)} ${formatKg(move.from)} → ${formatKg(move.to)}kg`;
  if (weekCount > 0) return `本周训练 ${weekCount} 次`;
  return "本周还没有完成的训练";
}

export function insightDetail(profile: Profile): string {
  const parts = selectedPartLabels(profile.injuries || []);
  const avoided = (profile.avoid_exercises || []).filter(Boolean);
  const bits: string[] = [];
  if (parts.length) bits.push(`${parts.join("、")}已自动避开`);
  if (avoided.length) {
    const shown = avoided.slice(0, 2).join("、");
    const more = avoided.length > 2 ? `等 ${avoided.length} 个动作` : "";
    bits.push(`排除${shown}${more}`);
  }
  // TODO: 「做完疼」14 天冷却和部位恢复窗口没有现成接口。规格禁止在这页重算，所以不编天数。
  if (!bits.length) return "按当前画像排接下来的课。";
  return `${bits.join("，")}。`;
}

const EXTRAS_KEY = "gym-coach-profile-extras";

export type ProfileExtras = {
  gender: string | null;
  /** YYYY-MM-DD；用来算年龄（热量等）。兼容旧字段 birthYear。 */
  birthDate: string | null;
};

function normalizeBirthDate(raw: { birthDate?: unknown; birthYear?: unknown }): string | null {
  if (typeof raw.birthDate === "string" && /^\d{4}-\d{2}-\d{2}$/.test(raw.birthDate)) {
    return raw.birthDate;
  }
  // 旧版只存了出生年 → 当成当年 1 月 1 日，编辑页可再改准
  if (typeof raw.birthYear === "number" && raw.birthYear > 1900 && raw.birthYear < 2020) {
    return `${raw.birthYear}-01-01`;
  }
  return null;
}

export function ageFromBirthDate(iso: string | null, today = new Date()): number | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  let age = today.getFullYear() - y;
  const beforeBirthday =
    today.getMonth() + 1 < mo || (today.getMonth() + 1 === mo && today.getDate() < d);
  if (beforeBirthday) age -= 1;
  if (age < 5 || age > 100) return null;
  return age;
}

export function formatBirthDateLabel(iso: string | null): string {
  if (!iso) return "未填";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const age = ageFromBirthDate(iso);
  const date = `${m[1]}.${m[2]}.${m[3]}`;
  return age != null ? `${date} · ${age}岁` : date;
}

export function readProfileExtras(): ProfileExtras {
  try {
    const raw = localStorage.getItem(EXTRAS_KEY);
    if (!raw) return { gender: null, birthDate: null };
    const parsed = JSON.parse(raw) as { gender?: unknown; birthDate?: unknown; birthYear?: unknown };
    const gender = parsed.gender === "男" || parsed.gender === "女" ? parsed.gender : null;
    return { gender, birthDate: normalizeBirthDate(parsed) };
  } catch {
    return { gender: null, birthDate: null };
  }
}

export function writeProfileExtras(extras: ProfileExtras) {
  // TODO: 性别、出生日期还不在 /api/profile。先记本机，热量阶段再入库。
  localStorage.setItem(EXTRAS_KEY, JSON.stringify(extras));
}

export function clearProfileExtras() {
  localStorage.removeItem(EXTRAS_KEY);
}
