/** 与后端动作目录 category / 伤痛词表对齐的选项 */

export const GOALS = [
  { value: "增肌" as const, sub: "吃够蛋白，力量慢慢涨" },
  { value: "减脂" as const, sub: "练着掉脂，保住肌肉" },
  { value: "力量" as const, sub: "主项重量优先" },
  { value: "塑形" as const, sub: "容量均衡，兼顾体态" },
];

export const EXPERIENCES = [
  { value: "新手" as const, sub: "刚开始系统练，动作还在学" },
  { value: "进阶" as const, sub: "有基础，能稳定推进" },
  { value: "老炮" as const, sub: "经验足，计划要更细" },
];

/** 器械偏好 → 动作库 category */
export const EQUIPMENT_OPTIONS = [
  { value: "自由重量", sub: "杠铃 / 哑铃 / 壶铃" },
  { value: "器械", sub: "固定轨迹器械、史密斯" },
  { value: "绳索", sub: "龙门架、绳索夹胸/面拉" },
  { value: "自重", sub: "徒手、引体、俯卧撑" },
] as const;

export type EquipmentTag = (typeof EQUIPMENT_OPTIONS)[number]["value"];

export const DEFAULT_EQUIPMENT: EquipmentTag[] = [
  "自由重量",
  "器械",
  "绳索",
  "自重",
];

export const INJURY_PRESETS = ["膝盖", "腰", "肩", "手腕", "肘", "踝"] as const;

export const SESSION_MINUTE_OPTIONS = [30, 45, 60, 75, 90] as const;

export const DEFAULT_PROFILE_CREATE = {
  goal: "增肌" as const,
  experience: "进阶" as const,
  weight_kg: 70,
  height_cm: null as number | null,
  days_per_week: 4,
  session_minutes: 45,
  injuries: [] as string[],
  preferences: [...DEFAULT_EQUIPMENT] as string[],
};
