import type { PlanTemplateCard } from "../types";

const GENERIC_AUTHORS = new Set(["Gym Coach", "GymCoach", "内容工坊", "系统", "官方"]);
/** 不当角标的占位词（类型/来源，不是运营卖点）。 */
const GENERIC_BADGES = new Set([
  "框架",
  "工坊",
  "系统",
  "官方",
  "fixed",
  "framework",
  "Gym Coach",
  "GymCoach",
  "内容工坊",
]);

/** 封面上的部位行：优先 muscle_tags，否则 split_summary。 */
export function planMuscleLine(plan: PlanTemplateCard, max = 4): string | null {
  const tags = (plan.muscle_tags || []).map((t) => String(t).trim()).filter(Boolean).slice(0, max);
  if (tags.length > 0) return tags.join(" · ");
  const split = plan.split_summary?.trim();
  return split || null;
}

/** 封面角标：有卖点的 badge_label（博主名 / 加强版…）；占位词不展示。 */
export function planCornerBadge(plan: PlanTemplateCard): string | null {
  const badge = plan.badge_label?.trim();
  if (!badge || GENERIC_BADGES.has(badge)) return null;
  return badge;
}

/**
 * 频次文案。
 * 单板块或每周 1 练 →「当日练」；多日 →「每周 N 练」。
 */
export function planCadenceLabel(plan: PlanTemplateCard): string {
  const singleDay =
    (plan.block_count != null && plan.block_count <= 1) || Number(plan.days_per_week) <= 1;
  if (singleDay) {
    return plan.minutes_label ? `当日练 · ${plan.minutes_label}` : "当日练";
  }
  const days = Number(plan.days_per_week) || 0;
  return days > 0 ? `每周 ${days} 练` : plan.minutes_label || "训练计划";
}

/** 干净署名；误填成分化短句的不返回。 */
export function planCredit(plan: PlanTemplateCard): string | null {
  const author = plan.author?.trim();
  if (!author || GENERIC_AUTHORS.has(author)) return null;
  if (author.includes("·") && author.split("·").filter(Boolean).length >= 2) return null;
  return author;
}
