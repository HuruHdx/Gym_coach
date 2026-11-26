type Props = {
  primary: string | null | undefined;
  secondary: string[];
  subRegion?: string | null;
};

const REGION_HINT: Record<string, string> = {
  胸: "正面中上",
  背: "背面中上",
  肩: "肩带两侧",
  腿: "下肢",
  臂: "上肢",
  核心: "躯干中段",
};

export function MuscleFocusDiagram({ primary, secondary, subRegion }: Props) {
  const main = (primary || "").trim() || null;
  const extras = secondary.filter((m) => m && m !== main);

  if (!main && extras.length === 0) {
    return (
      <div className="rounded-xl border border-line bg-elevated px-3.5 py-3">
        <h2 className="text-[13px] font-extrabold">发力部位</h2>
        <p className="mt-1.5 text-[12px] text-muted">暂无主练肌群标注。</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-line bg-elevated px-3.5 py-3">
      <h2 className="text-[13px] font-extrabold">发力部位</h2>
      <div className="mt-2.5 flex gap-3">
        <div className="grid h-[88px] w-[72px] shrink-0 place-items-center rounded-xl bg-gradient-to-b from-[var(--hero-a)] to-bg text-center">
          <div>
            <p className="text-[18px] font-extrabold text-accent-text">{main || "—"}</p>
            <p className="mt-0.5 text-[10px] text-muted">
              {main ? REGION_HINT[main] || "主练" : ""}
            </p>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[12px] text-ink">
            <span className="font-bold">主练</span>
            {" · "}
            {main || "—"}
            {subRegion ? `（${subRegion}）` : ""}
          </p>
          <p className="mt-1.5 text-[12px] text-muted">
            <span className="font-bold text-ink">协同</span>
            {" · "}
            {extras.length > 0 ? extras.join("、") : "未标注"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {main ? (
              <span className="rounded-md bg-tint px-2 py-0.5 text-[10.5px] font-bold text-accent-text">
                主 {main}
              </span>
            ) : null}
            {extras.slice(0, 4).map((m) => (
              <span
                key={m}
                className="rounded-md border border-line bg-bg px-2 py-0.5 text-[10.5px] font-bold text-muted"
              >
                协 {m}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
