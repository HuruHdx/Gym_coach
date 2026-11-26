import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { MusclePulse } from "../../types";

const MUSCLES = ["胸", "背", "肩", "腿", "臂", "核心"] as const;

type Face = "front" | "back";

type Props = {
  pulse: MusclePulse[] | undefined | null;
};

function intensityClass(count: number, max: number): string {
  if (count <= 0 || max <= 0) return "fill-[var(--line)] opacity-40";
  const ratio = count / max;
  if (ratio >= 0.75) return "fill-[var(--accent)] opacity-95";
  if (ratio >= 0.45) return "fill-[var(--accent)] opacity-70";
  if (ratio >= 0.2) return "fill-[var(--accent)] opacity-45";
  return "fill-[var(--accent)] opacity-25";
}

export function MuscleHeatmapCard({ pulse }: Props) {
  const [face, setFace] = useState<Face>("front");
  const [active, setActive] = useState<string | null>(null);

  const byMuscle = useMemo(() => {
    const map = new Map<string, MusclePulse>();
    for (const row of pulse || []) {
      if (row.muscle) map.set(row.muscle, row);
    }
    return map;
  }, [pulse]);

  const maxCount = useMemo(
    () => Math.max(0, ...MUSCLES.map((m) => byMuscle.get(m)?.count_30d ?? 0)),
    [byMuscle],
  );

  const hasHistory = MUSCLES.some((m) => (byMuscle.get(m)?.count_30d ?? 0) > 0);
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
        <svg viewBox="0 0 120 200" className="h-[180px] w-[108px] shrink-0" aria-hidden>
          {/* torso outline */}
          <ellipse cx="60" cy="22" rx="16" ry="18" className="fill-[var(--elevated)] stroke-[var(--line)]" strokeWidth="1.5" />
          {/* shoulders */}
          <path
            d={face === "front" ? "M28 48 Q60 36 92 48 L86 68 Q60 58 34 68 Z" : "M28 48 Q60 36 92 48 L86 68 Q60 58 34 68 Z"}
            className={`${intensityClass(byMuscle.get("肩")?.count_30d ?? 0, maxCount)} stroke-[var(--line)]`}
            strokeWidth="1"
            onClick={() => setActive("肩")}
            role="button"
          />
          {/* chest / back */}
          <path
            d="M36 66 Q60 58 84 66 L80 108 Q60 118 40 108 Z"
            className={`${intensityClass(
              (face === "front" ? byMuscle.get("胸") : byMuscle.get("背"))?.count_30d ?? 0,
              maxCount,
            )} stroke-[var(--line)]`}
            strokeWidth="1"
            onClick={() => setActive(face === "front" ? "胸" : "背")}
            role="button"
          />
          {/* core */}
          <path
            d="M44 108 Q60 112 76 108 L74 138 Q60 146 46 138 Z"
            className={`${intensityClass(byMuscle.get("核心")?.count_30d ?? 0, maxCount)} stroke-[var(--line)]`}
            strokeWidth="1"
            onClick={() => setActive("核心")}
            role="button"
          />
          {/* arms */}
          <path
            d="M28 52 L18 110 L28 112 L36 68 Z"
            className={`${intensityClass(byMuscle.get("臂")?.count_30d ?? 0, maxCount)} stroke-[var(--line)]`}
            strokeWidth="1"
            onClick={() => setActive("臂")}
            role="button"
          />
          <path
            d="M92 52 L102 110 L92 112 L84 68 Z"
            className={`${intensityClass(byMuscle.get("臂")?.count_30d ?? 0, maxCount)} stroke-[var(--line)]`}
            strokeWidth="1"
            onClick={() => setActive("臂")}
            role="button"
          />
          {/* legs */}
          <path
            d="M46 140 L40 190 L54 190 L58 142 Z"
            className={`${intensityClass(byMuscle.get("腿")?.count_30d ?? 0, maxCount)} stroke-[var(--line)]`}
            strokeWidth="1"
            onClick={() => setActive("腿")}
            role="button"
          />
          <path
            d="M62 142 L66 190 L80 190 L74 140 Z"
            className={`${intensityClass(byMuscle.get("腿")?.count_30d ?? 0, maxCount)} stroke-[var(--line)]`}
            strokeWidth="1"
            onClick={() => setActive("腿")}
            role="button"
          />
        </svg>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap gap-1.5">
            {MUSCLES.map((m) => {
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
                    {" · "}距上次 <span className="num font-bold text-ink">{selected.days_since}</span> 天
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
