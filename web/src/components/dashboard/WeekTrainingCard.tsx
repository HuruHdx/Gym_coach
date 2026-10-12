import { Link } from "react-router-dom";
import type { WeekTrainingSummary } from "../../lib/trainingAnalytics";

type Props = {
  week: WeekTrainingSummary;
  onDayClick?: (sessionId: number) => void;
};

/** 本周训练看板卡：7 天点亮 + 部位分布，后续可并排加热量卡 */
export function WeekTrainingCard({ week, onDayClick }: Props) {
  const pct = Math.min(100, Math.round((week.trainedDays / week.targetDays) * 100));

  return (
    <section className="rounded-2xl border border-line bg-elevated px-4 py-4 rise-in">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted">本周训练</p>
          <p className="font-display mt-1 text-2xl font-extrabold tracking-tight">
            <span className="font-num">{week.trainedDays}</span>
            <span className="mx-1 text-base text-muted">/</span>
            <span className="font-num text-lg text-muted">{week.targetDays}</span>
            <span className="ml-1.5 text-sm font-bold text-muted">天</span>
          </p>
          <p className="mt-1 text-xs text-muted">
            {week.sessions > 0
              ? `${week.sessions} 场 · ${week.muscles.length ? week.muscles.join("、") : "部位待标注"}`
              : "本周还没开练，去教练排一堂"}
          </p>
        </div>
        <Link
          to="/training"
          className="pressable shrink-0 rounded-md border border-line px-3 py-2 text-xs font-bold"
        >
          明细 →
        </Link>
      </div>

      <div className="mt-3 h-1 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-4 grid grid-cols-7 gap-1.5">
        {week.days.map((d) => {
          const clickable = Boolean(d.sessionId && onDayClick);
          const Tag = clickable ? "button" : "div";
          return (
            <Tag
              key={d.date}
              type={clickable ? "button" : undefined}
              onClick={
                clickable && d.sessionId
                  ? () => onDayClick?.(d.sessionId!)
                  : undefined
              }
              className={`flex flex-col items-center rounded-lg py-2 ${
                d.trained
                  ? "bg-ink text-accent"
                  : d.isToday
                    ? "border border-ink/30 bg-bg"
                    : "bg-bg/80"
              } ${clickable ? "pressable" : ""}`}
            >
              <span
                className={`text-[10px] font-bold ${
                  d.trained ? "text-accent/80" : "text-muted"
                }`}
              >
                {d.label}
              </span>
              <span
                className={`mt-1 font-display text-xs font-extrabold ${
                  d.trained ? "text-accent" : d.isToday ? "text-ink" : "text-muted"
                }`}
              >
                {d.trained
                  ? d.muscles[0]?.slice(0, 1) || "练"
                  : d.isToday
                    ? "今"
                    : "·"}
              </span>
            </Tag>
          );
        })}
      </div>

      {week.muscles.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {week.muscles.map((m) => (
            <span
              key={m}
              className="rounded-md border border-line bg-bg px-2 py-0.5 text-[10px] font-bold text-muted"
            >
              {m}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
