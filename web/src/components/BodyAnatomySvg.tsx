/** 六大肌群人体解剖示意（纯内联 SVG，无外链）。 */

export const BODY_MUSCLES = ["胸", "背", "肩", "腿", "臂", "核心"] as const;
export type BodyMuscle = (typeof BODY_MUSCLES)[number];
export type BodyFace = "front" | "back";

export type BodyAnatomyMode = "heatmap" | "focus";

type Props = {
  mode: BodyAnatomyMode;
  face: BodyFace;
  /** heatmap: 各肌群热度 0～1；focus: 主练 1 / 协同 ~0.45 */
  levels: Partial<Record<BodyMuscle, number>>;
  active?: string | null;
  onSelect?: (muscle: BodyMuscle) => void;
  className?: string;
  /** 紧凑双小人用更小尺寸 */
  compact?: boolean;
};

function fillFor(level: number, active: boolean): string {
  if (level <= 0) return "var(--line)";
  if (active) return "var(--accent)";
  if (level >= 0.75) return "color-mix(in srgb, var(--accent) 95%, transparent)";
  if (level >= 0.45) return "color-mix(in srgb, var(--accent) 70%, transparent)";
  if (level >= 0.2) return "color-mix(in srgb, var(--accent) 45%, transparent)";
  return "color-mix(in srgb, var(--accent) 28%, transparent)";
}

function opacityFor(level: number): number {
  if (level <= 0) return 0.35;
  return 1;
}

/** 将中文肌群 / 别名归一到六大类 */
export function normalizeBodyMuscle(raw: string | null | undefined): BodyMuscle | null {
  const t = (raw || "").trim();
  if (!t) return null;
  if ((BODY_MUSCLES as readonly string[]).includes(t)) return t as BodyMuscle;
  if (/胸| pec/i.test(t)) return "胸";
  if (/背|阔背|斜方|竖脊/i.test(t)) return "背";
  if (/肩|三角/i.test(t)) return "肩";
  if (/腿|股|臀|腘|小腿|腘绳/i.test(t)) return "腿";
  if (/臂|二头|三头|前臂|肱/i.test(t)) return "臂";
  if (/核心|腹|腰/i.test(t)) return "核心";
  return null;
}

export function preferredFaceForMuscle(muscle: BodyMuscle | null): BodyFace {
  if (muscle === "背") return "back";
  return "front";
}

export function BodyAnatomySvg({
  mode,
  face,
  levels,
  active,
  onSelect,
  className,
  compact,
}: Props) {
  const clickable = Boolean(onSelect);
  const stroke = "var(--line)";
  const silhouette = "var(--surface)";

  function region(muscle: BodyMuscle, d: string) {
    // 正面胸、背面背；肩/臂/腿/核心双面都有
    if (muscle === "胸" && face !== "front") return null;
    if (muscle === "背" && face !== "back") return null;
    const level = levels[muscle] ?? 0;
    const isActive = active === muscle;
    return (
      <path
        key={`${face}-${muscle}-${d.slice(0, 12)}`}
        d={d}
        fill={fillFor(level, isActive)}
        fillOpacity={opacityFor(level)}
        stroke={isActive ? "var(--accent)" : stroke}
        strokeWidth={isActive ? 1.6 : 1}
        className={clickable ? "cursor-pointer transition-[fill,opacity] duration-150" : undefined}
        role={clickable ? "button" : undefined}
        tabIndex={clickable ? 0 : undefined}
        onClick={
          clickable
            ? (e) => {
                e.stopPropagation();
                onSelect?.(muscle);
              }
            : undefined
        }
        onKeyDown={
          clickable
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect?.(muscle);
                }
              }
            : undefined
        }
      />
    );
  }

  return (
    <svg
      viewBox="0 0 120 220"
      className={className || (compact ? "h-[120px] w-[66px]" : "h-[200px] w-[110px]")}
      aria-hidden={mode === "focus" ? true : undefined}
      aria-label={mode === "heatmap" ? `人体${face === "front" ? "正面" : "背面"}热力` : undefined}
    >
      {/* 外轮廓剪影 */}
      <ellipse cx="60" cy="22" rx="15" ry="17" fill={silhouette} stroke={stroke} strokeWidth="1.2" />
      <path
        d="M32 48 C40 38 80 38 88 48 L94 72 C96 88 92 100 88 112 L84 118 L36 118 L32 112 C28 100 24 88 26 72 Z"
        fill={silhouette}
        stroke={stroke}
        strokeWidth="1.2"
      />
      <path
        d="M36 118 L32 210 L50 210 L54 150 L66 150 L70 210 L88 210 L84 118 Z"
        fill={silhouette}
        stroke={stroke}
        strokeWidth="1.2"
      />

      {/* 肩 */}
      {region("肩", "M30 46 C44 34 76 34 90 46 L86 68 C72 58 48 58 34 68 Z")}
      {/* 胸 / 背躯干上 */}
      {region("胸", "M38 64 C52 56 68 56 82 64 L78 102 C66 112 54 112 42 102 Z")}
      {region("背", "M38 64 C52 56 68 56 82 64 L78 102 C66 112 54 112 42 102 Z")}
      {/* 核心 */}
      {region("核心", "M44 100 C56 96 64 96 76 100 L74 136 C62 146 58 146 46 136 Z")}
      {/* 臂 */}
      {region("臂", "M28 52 L14 118 L28 122 L38 70 Z")}
      {region("臂", "M92 52 L106 118 L92 122 L82 70 Z")}
      {/* 腿 */}
      {region("腿", "M40 138 L34 208 L52 208 L56 150 Z")}
      {region("腿", "M64 150 L68 208 L86 208 L80 138 Z")}

      {/* 简易关节点，增强人体感 */}
      <circle cx="60" cy="22" r="2.2" fill="var(--text-3, var(--muted))" opacity="0.35" />
    </svg>
  );
}
