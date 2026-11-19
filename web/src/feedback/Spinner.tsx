type Props = {
  size?: number;
  label?: string;
  className?: string;
};

/** 行内 / 按钮内小转圈 */
export function Spinner({ size = 14, label, className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-current ${className}`.trim()}
      role="status"
      aria-label={label || "加载中"}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
        className="animate-spin"
      >
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.4" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
      </svg>
      {label ? <span className="text-meta text-muted">{label}</span> : null}
    </span>
  );
}
