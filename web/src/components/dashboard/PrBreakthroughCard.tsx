import { Link } from "react-router-dom";
import type { PrHit } from "../../lib/trainingAnalytics";

type Props = {
  hits: PrHit[];
  onOpenSession?: (sessionId: number) => void;
  onOpenExercise?: (name: string) => void;
};

/** PR / 突破看板卡：场次突破 + 动作上涨，占位与热量卡同级 */
export function PrBreakthroughCard({ hits, onOpenSession, onOpenExercise }: Props) {
  return (
    <section className="rounded-2xl border border-line bg-elevated px-4 py-4 rise-in rise-in-delay-1">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted">力量突破</p>
          <p className="font-display mt-1 text-lg font-extrabold tracking-tight">
            {hits.length > 0 ? "最近在涨的动作" : "完成训练后会出现突破"}
          </p>
          <p className="mt-1 text-xs text-muted">
            按单个动作的重量对比，不是全场加总公斤数
          </p>
        </div>
        <Link
          to="/training"
          className="pressable shrink-0 rounded-md border border-line px-3 py-2 text-xs font-bold"
        >
          动作 →
        </Link>
      </div>

      {hits.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-line bg-bg/60 px-3 py-4 text-center text-xs text-muted">
          还没有突破记录。练完并勾满组次后，加重完成会记在这里。
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {hits.map((h, i) => {
            const clickable =
              (h.kind === "session" && h.sessionId && onOpenSession) ||
              (h.kind === "exercise" && h.exerciseName && onOpenExercise);
            return (
              <li key={`${h.kind}-${h.title}-${i}`}>
                <button
                  type="button"
                  disabled={!clickable}
                  onClick={() => {
                    if (h.kind === "session" && h.sessionId) onOpenSession?.(h.sessionId);
                    if (h.kind === "exercise" && h.exerciseName)
                      onOpenExercise?.(h.exerciseName);
                  }}
                  className={`flex w-full items-center justify-between gap-2 rounded-xl border border-line bg-bg px-3 py-2.5 text-left ${
                    clickable ? "pressable hover:border-ink/30" : ""
                  } disabled:opacity-100`}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="rounded bg-ink px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-accent">
                        {h.kind === "session" ? "场次" : "动作"}
                      </span>
                      <span className="font-display truncate text-sm font-bold">{h.title}</span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-muted">{h.subtitle}</p>
                  </div>
                  <div className="shrink-0 text-right text-[11px] font-bold text-muted">
                    {h.date || "走势 ↑"}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
