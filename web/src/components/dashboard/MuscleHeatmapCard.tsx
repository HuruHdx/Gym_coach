import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { MusclePulse } from "../../types";
import {
  BODY_MUSCLES,
  BodyAnatomySvg,
  type BodyFace,
  type BodyMuscle,
} from "../BodyAnatomySvg";

type Props = {
  pulse: MusclePulse[] | undefined | null;
};

export function MuscleHeatmapCard({ pulse }: Props) {
  const [face, setFace] = useState<BodyFace>("front");
  const [active, setActive] = useState<string | null>(null);

  const byMuscle = useMemo(() => {
    const map = new Map<string, MusclePulse>();
    for (const row of pulse || []) {
      if (row.muscle) map.set(row.muscle, row);
    }
    return map;
  }, [pulse]);

  const maxCount = useMemo(
    () => Math.max(0, ...BODY_MUSCLES.map((m) => byMuscle.get(m)?.count_30d ?? 0)),
    [byMuscle],
  );

  const levels = useMemo(() => {
    const out: Partial<Record<BodyMuscle, number>> = {};
    for (const m of BODY_MUSCLES) {
      const c = byMuscle.get(m)?.count_30d ?? 0;
      out[m] = maxCount > 0 ? c / maxCount : 0;
    }
    return out;
  }, [byMuscle, maxCount]);

  const hasHistory = BODY_MUSCLES.some((m) => (byMuscle.get(m)?.count_30d ?? 0) > 0);
  const selected = active ? byMuscle.get(active) : null;

  if (!hasHistory) {
    return (
      <div className="border-t border-line py-3">
        <p className="text-[13px] text-muted">
          还没有部位记录。去今日页练几场后，这里会显示近期分布。
        </p>
        <Link to="/" className="mt-2 inline-block text-[12px] font-bold text-accent-text">
          去今日 ›
        </Link>
      </div>
    );
  }

  return (
    <div className="border-t border-line py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex rounded-full border border-line bg-elevated p-0.5">
          {(
            [
              ["front", "正面"],
              ["back", "背面"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFace(id)}
              className={`pressable rounded-full px-3 py-1 text-[11px] font-bold ${
                face === id ? "bg-accent text-accent-ink" : "text-muted"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-[10.5px] text-muted">近 30 天 · 点部位看明细</p>
      </div>

      <div className="mt-3 flex items-start gap-3">
        <BodyAnatomySvg
          mode="heatmap"
          face={face}
          levels={levels}
          active={active}
          onSelect={(m) => setActive(m)}
        />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap gap-1.5">
            {BODY_MUSCLES.map((m) => {
              const row = byMuscle.get(m);
              const count = row?.count_30d ?? 0;
              const on = active === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => setActive(m)}
                  className={`pressable rounded-full border px-2.5 py-1 text-[11px] font-bold ${
                    on
                      ? "border-accent bg-tint text-accent-text"
                      : "border-line bg-elevated text-muted"
                  }`}
                >
                  {m}
                  <span className="num ml-1 opacity-80">{count}</span>
                </button>
              );
            })}
          </div>

          {selected && active ? (
            <div className="mt-3 rounded-xl border border-line bg-elevated px-3 py-2.5">
              <p className="text-[13px] font-extrabold text-ink">{active}</p>
              <p className="mt-1 text-[12px] text-muted">
                近 30 天练了 <span className="num font-bold text-ink">{selected.count_30d}</span> 次
                {selected.days_since != null ? (
                  <>
                    {" · "}距上次 <span className="num font-bold text-ink">{selected.days_since}</span>{" "}
                    天
                  </>
                ) : null}
                {selected.trend ? ` · 趋势 ${selected.trend}` : ""}
              </p>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] font-bold">
                <Link to={`/exercises?muscle=${encodeURIComponent(active)}`} className="text-accent-text">
                  去动作库看动作 ›
                </Link>
                <Link
                  to="/coach"
                  state={{ preset: `今天练${active}` }}
                  className="text-accent-text"
                >
                  让教练排一场 ›
                </Link>
              </div>
            </div>
          ) : (
            <p className="mt-3 text-[12px] text-muted">点人体或胶囊查看该部位明细。</p>
          )}
        </div>
      </div>
    </div>
  );
}
