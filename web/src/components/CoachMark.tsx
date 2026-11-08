/** 燃燃的标记。对话头像和页头用同一枚，不再写「AI」。 */
export function CoachMark({ className = "h-7 w-7 text-micro" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`grid shrink-0 place-items-center rounded-full bg-tint font-display font-semibold text-accent-text ${className}`}
    >
      燃
    </span>
  );
}
