/**
 * 画像选项：唯一来源。
 * 字段与取值见《训练计划规则与画像.md》4.1 / 4.2 / 4.5。
 * 其他页面（我的 / 编辑资料）从这里取，不要各写一份。
 */

import type { Experience, Goal } from "../types";

/** 4.1-1 目标 → 次数区间与强度区间 */
export const GOALS: { value: Goal; sub: string }[] = [
  { value: "增肌", sub: "8~12 次，留 1~2 次余力" },
  { value: "减脂", sub: "10~15 次，组间歇短" },
  { value: "力量", sub: "3~6 次，主项优先" },
  { value: "塑形", sub: "12~15 次，容量均衡" },
];

export const GOAL_OPTIONS: Goal[] = GOALS.map((item) => item.value);

/** 4.1-2 经验 → 容量、重量步进、动作复杂度 */
export const EXPERIENCES: { value: Experience; sub: string }[] = [
  { value: "新手", sub: "0~6 个月 · 动作还在学，先求稳" },
  { value: "进阶", sub: "半年~2 年 · 能独立完成复合动作" },
  { value: "老炮", sub: "3 年以上 · 计划要能精细调" },
];

export const EXPERIENCE_OPTIONS: { value: Experience; label: string }[] = EXPERIENCES.map((item) => ({
  value: item.value,
  label: item.value,
}));

/** 4.1-3 每周天数（2~7）。只参与单次容量，不做周配额。 */
export const DAY_OPTIONS = [2, 3, 4, 5, 6, 7] as const;

/** 4.1-4 单次时长 → 动作个数（40 约 4 个，60 约 5，90 约 7） */
export const SESSION_MINUTE_OPTIONS = [40, 60, 75, 90] as const;

export function exercisesForMinutes(minutes: number): string {
  if (minutes <= 45) return "约 4 个动作";
  if (minutes <= 65) return "约 5 个动作";
  return "约 7 个动作";
}

/** 4.1-6 伤病：部位多选。取值必须能在后端 INJURY_NAME_KEYWORDS 里命中。 */
export const INJURY_PRESETS = ["膝盖", "腰", "肩", "手腕", "肘"] as const;

/**
 * 器械标签 → 动作库 category。
 * 引导页已改成「场景」三选一，不再让人逐个勾器械；这里保留导出只为兼容旧引用。
 */
export const EQUIPMENT_OPTIONS = [
  { value: "自由重量", sub: "杠铃 / 哑铃 / 壶铃" },
  { value: "器械", sub: "固定轨迹器械、史密斯" },
  { value: "绳索", sub: "龙门架、绳索夹胸/面拉" },
  { value: "自重", sub: "徒手、引体、俯卧撑" },
] as const;

export type EquipmentTag = (typeof EQUIPMENT_OPTIONS)[number]["value"];

export const DEFAULT_EQUIPMENT: EquipmentTag[] = ["自由重量", "器械", "绳索", "自重"];

export type SceneId = "gym" | "home" | "bodyweight";

/**
 * 4.1-5 场景 → 候选动作池。
 * preferences 是场景的投影，不是独立字段：存库仍写 preferences（器械标签），
 * 但只允许这三个规范集合，避免「自由勾选 → 读回失真 → 再保存被放大」。
 */
export const SCENES: {
  id: SceneId;
  title: string;
  sub: string;
  preferences: string[];
}[] = [
  {
    id: "gym",
    title: "健身房",
    sub: "杠铃 / 哑铃 / 固定器械 / 绳索",
    preferences: ["自由重量", "器械", "绳索", "自重"],
  },
  {
    id: "home",
    title: "家里有哑铃",
    sub: "哑铃 / 弹力带 / 单杠",
    // 现有器械标签没有「弹力带」，居家落到自由重量 + 自重。
    preferences: ["自由重量", "自重"],
  },
  {
    id: "bodyweight",
    title: "纯徒手",
    sub: "无器械，自重为主",
    preferences: ["自重"],
  },
];

export function preferencesForScene(id: SceneId): string[] {
  const scene = SCENES.find((item) => item.id === id) ?? SCENES[0];
  return [...scene.preferences];
}

/** 把库里存的 preferences 读回成场景。不匹配任何规范集合时按健身房处理。 */
export function sceneFromPreferences(prefs: string[] | null | undefined): SceneId {
  const set = new Set(prefs || []);
  const exact = SCENES.find(
    (scene) => scene.preferences.length === set.size && scene.preferences.every((tag) => set.has(tag)),
  );
  return exact?.id ?? "gym";
}

/** 跳过引导时的默认画像。 */
export const DEFAULT_PROFILE_CREATE = {
  goal: "增肌" as const,
  experience: "进阶" as const,
  weight_kg: 70,
  height_cm: null as number | null,
  days_per_week: 4,
  session_minutes: 40,
  injuries: [] as string[],
  preferences: preferencesForScene("gym"),
};
