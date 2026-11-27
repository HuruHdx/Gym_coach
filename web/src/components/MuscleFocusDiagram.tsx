import { useMemo } from "react";
import {
  BodyAnatomySvg,
  normalizeBodyMuscle,
  preferredFaceForMuscle,
  type BodyMuscle,
} from "./BodyAnatomySvg";

type Props = {
  primary: string | null | undefined;
  secondary: string[];
  subRegion?: string | null;
};

export function MuscleFocusDiagram({ primary, secondary, subRegion }: Props) {
  const mainRaw = (primary || "").trim() || null;
  const main = normalizeBodyMuscle(mainRaw);
  const extrasRaw = secondary.filter((m) => m && m !== mainRaw);
  const extras = extrasRaw
    .map((m) => normalizeBodyMuscle(m))
    .filter((m): m is BodyMuscle => Boolean(m) && m !== main);

  const levels = useMemo(() => {
    const out: Partial<Record<BodyMuscle, number>> = {};
    if (main) out[main] = 1;
    for (const m of extras) out[m] = Math.max(out[m] ?? 0, 0.42);
    return out;
  }, [main, extras]);

  const frontLevels = useMemo(() => {
    const out: Partial<Record<BodyMuscle, number>> = {};
    for (const [k, v] of Object.entries(levels) as [BodyMuscle, number][]) {
      if (k === "背") continue;
      out[k] = v;
    }
    return out;
  }, [levels]);

  const backLevels = useMemo(() => {
    const out: Partial<Record<BodyMuscle, number>> = {};
    for (const [k, v] of Object.entries(levels) as [BodyMuscle, number][]) {
      if (k === "胸") continue;
      // 背面也画肩臂腿核心轮廓强度
      out[k] = v;
    }
    return out;
  }, [levels]);

  if (!mainRaw && extrasRaw.length === 0) {
    return (
      <div className="rounded-xl border border-line bg-elevated px-3.5 py-3">
        <h2 className="text-[13px] font-extrabold">发力部位</h2>
        <p className="mt-1.5 text-[12px] text-muted">暂无主练肌群标注。</p>
      </div>
    );
  }

  const preferBack = preferredFaceForMuscle(main) === "back";

  return (
    <div className="rounded-xl border border-line bg-elevated px-3.5 py-3">
      <h2 className="text-[13px] font-extrabold">发力部位</h2>
      <div className="mt-2.5 flex gap-3">
        <div className="flex shrink-0 gap-1.5 rounded-xl bg-bg px-1.5 py-1.5">
          <div className={preferBack ? "opacity-55" : ""}>
            <BodyAnatomySvg
              mode="focus"
              face="front"
              levels={frontLevels}
              active={main}
              compact
            />
            <p className="mt-0.5 text-center text-[9px] font-bold text-muted">正</p>
          </div>
          <div className={preferBack ? "" : "opacity-55"}>
            <BodyAnatomySvg
              mode="focus"
              face="back"
              levels={backLevels}
              active={main}
              compact
            />
            <p className="mt-0.5 text-center text-[9px] font-bold text-muted">背</p>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[12px] text-ink">
            <span className="font-bold">主练</span>
            {" · "}
            {mainRaw || "—"}
            {subRegion ? `（${subRegion}）` : ""}
          </p>
          <p className="mt-1.5 text-[12px] text-muted">
            <span className="font-bold text-ink">协同</span>
            {" · "}
            {extrasRaw.length > 0 ? extrasRaw.join("、") : "未标注"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {mainRaw ? (
              <span className="rounded-md bg-tint px-2 py-0.5 text-[10.5px] font-bold text-accent-text">
                主 {mainRaw}
              </span>
            ) : null}
            {extrasRaw.slice(0, 4).map((m) => (
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
