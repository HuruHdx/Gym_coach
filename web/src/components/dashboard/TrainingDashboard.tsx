import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { KeyLift, TrainingDashboard as DashboardData, WeekRhythm } from "../../types";
import { TrendMark } from "../training/TrendMark";

export type DashboardPeriod = "week" | "month";

type Props = {
  data: DashboardData;
  period?: DashboardPeriod;
  onPeriodChange?: (period: DashboardPeriod) => void;
  onOpenSession?: (sessionId: number) => void;
  onOpenExercise?: (name: string) => void;
  onSeeAllLifts?: () => void;
  activityLine?: string | null;
};

export function TrainingDashboard({
  data,
  period = "week",
  onPeriodChange,
  onOpenSession,
  onOpenExercise,
  onSeeAllLifts,
  activityLine,
}: Props) {
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="space-y-3 rise-in">
      <section className="rounded-2xl border border-line bg-elevated px-4 py-3.5">
        <div className="flex items-start gap-4">
          <button
            type="button"
            onClick={() => setCalendarOpen((open) => !open)}
            className="pressable shrink-0"
            aria-expanded={calendarOpen}
            aria-label={calendarOpen ? "收起日历" : "展开日历"}
          >
            <WeekRing trained={data.week.trained_days} target={data.week.target_days} />
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <p className="text-[11px] font-bold text-muted">
                {period === "month" ? "本月训练" : "本周训练"}
              </p>
              {onPeriodChange && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setMenuOpen((open) => !open)}
                    className="pressable inline-flex items-center gap-0.5 text-[11px] font-extrabold text-ink"
                  >
                    {period === "month" ? "月" : "周"}
                    <ChevronDown size={14} />
                  </button>
                  {menuOpen && (
                    <div className="absolute right-0 z-10 mt-1 w-16 overflow-hidden rounded-lg border border-line bg-bg shadow-lg">
                      {(["week", "month"] as const).map((item) => (
                        <button
                          key={item}
                          type="button"
                          onClick={() => {
                            onPeriodChange(item);
                            setMenuOpen(false);
                          }}
                          className={`block w-full px-3 py-2 text-left text-[11px] font-extrabold ${
                            period === item ? "bg-ink text-accent" : "text-ink"
                          }`}
                        >
                          {item === "month" ? "月" : "周"}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <p className="mt-0.5 font-display text-sm font-bold leading-snug">
              已完成 {data.week.trained_days}/{data.week.target_days} 天
            </p>
            <p className="mt-1 text-[13px] font-bold leading-snug text-ink">{data.headline}</p>
            {activityLine && <p className="mt-1 text-[11px] text-muted">{activityLine}</p>}
          </div>
        </div>
        {calendarOpen && (
          <div className="mt-3 border-t border-line/80 pt-3">
            <WeekStrip week={data.week} onDayClick={(id) => onOpenSession?.(id)} />
          </div>
        )}
      </section>

      {data.key_lifts.length > 0 && (
        <section className="rounded-2xl border border-line bg-elevated px-3.5 py-3.5">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-bold text-muted">主力动作进阶</p>
            {onSeeAllLifts && (
              <button
                type="button"
                onClick={onSeeAllLifts}
                className="pressable inline-flex items-center text-[11px] font-extrabold text-muted"
              >
                全部
                <ChevronRight size={16} />
              </button>
            )}
          </div>
          <ul className="mt-2 divide-y divide-line/80">
            {data.key_lifts.slice(0, 3).map((lift) => (
              <LiftRow key={lift.exercise_name} lift={lift} onOpen={onOpenExercise} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function LiftRow({
  lift,
  onOpen,
}: {
  lift: KeyLift;
  onOpen?: (name: string) => void;
}) {
  const trend = lift.delta_kg > 0.01 ? "up" : lift.delta_kg < -0.01 ? "down" : "flat";
  return (
    <li>
      <button
        type="button"
        disabled={!onOpen}
        onClick={() => onOpen?.(lift.exercise_name)}
        className={`flex w-full items-center justify-between gap-2 py-2.5 text-left ${
          onOpen ? "pressable" : ""
        }`}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="truncate text-sm font-bold">{lift.exercise_name}</p>
            <TrendMark trend={trend} />
            {lift.is_pr && (
              <span className="rounded bg-ink px-1 py-0.5 text-[9px] font-extrabold text-accent">PR</span>
            )}
          </div>
          <p className="font-num mt-0.5 text-[11px] text-muted">
            {lift.load}
            {lift.muscle ? ` · ${lift.muscle}` : ""}
          </p>
        </div>
        <Sparkline values={lift.history} />
      </button>
    </li>
  );
}

function WeekRing({ trained, target }: { trained: number; target: number }) {
  const pct = target > 0 ? Math.min(trained / target, 1) : 0;
  const R = 34;
  const C = 2 * Math.PI * R;
  const filled = C * pct;
  return (
    <svg width="84" height="84" viewBox="0 0 84 84">
      <circle cx="42" cy="42" r={R} fill="none" stroke="currentColor" strokeOpacity="0.12" strokeWidth="7" />
      <circle
        cx="42"
        cy="42"
        r={R}
        fill="none"
        stroke="currentColor"
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${C - filled}`}
        transform="rotate(-90 42 42)"
        className="text-ink"
      />
      <text x="42" y="40" textAnchor="middle" className="fill-ink font-num text-lg font-extrabold" dominantBaseline="middle">
        {trained}
      </text>
      <text x="42" y="55" textAnchor="middle" className="fill-muted text-[9px] font-bold" dominantBaseline="middle">
        / {target} 天
      </text>
    </svg>
  );
}

function WeekStrip({
  week,
  onDayClick,
}: {
  week: WeekRhythm;
  onDayClick?: (sessionId: number) => void;
}) {
  const month = week.period === "month";
  const lead =
    month && week.days.length > 0
      ? (new Date(`${week.days[0].date}T00:00:00`).getDay() + 6) % 7
      : 0;
  const cells: Array<WeekRhythm["days"][number] | null> = [
    ...Array.from({ length: lead }, () => null),
    ...week.days,
  ];
  return (
    <div>
      {month && (
        <div className="grid grid-cols-7 text-center text-[10px] font-bold text-muted">
          {["一", "二", "三", "四", "五", "六", "日"].map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
      )}
      <div className={`grid grid-cols-7 ${month ? "mt-1" : ""}`}>
        {cells.map((day, index) => {
          if (!day) return <div key={`pad-${index}`} />;
          const clickable = Boolean(day.session_id && onDayClick);
          const Tag = clickable ? "button" : "div";
          const dayNum = Number(day.date.slice(8));
          return (
            <Tag
              key={day.date}
              type={clickable ? "button" : undefined}
              onClick={clickable && day.session_id ? () => onDayClick?.(day.session_id!) : undefined}
              className={`flex flex-col items-center gap-1 py-1 ${clickable ? "pressable" : ""}`}
            >
              {!month && <span className="text-[11px] font-medium text-muted">{day.label}</span>}
              <span
                className={`grid place-items-center rounded-full font-num font-bold ${
                  month ? "h-7 w-7 text-[12px]" : "h-8 w-8 text-[13px]"
                } ${day.is_today ? "bg-ink text-bg" : day.trained ? "text-ink" : "text-muted"}`}
              >
                {day.is_today ? "今" : dayNum}
              </span>
              <span className={`h-1.5 w-1.5 rounded-full ${day.trained ? "bg-ink" : "bg-transparent"}`} />
            </Tag>
          );
        })}
      </div>
    </div>
  );
}

export function Sparkline({ values }: { values?: number[] }) {
  const points = (values || []).filter((n) => Number.isFinite(n));
  if (points.length < 2) return null;
  const w = 72;
  const h = 28;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const coords = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * (w - 4) + 2;
      const y = h - 3 - ((value - min) / span) * (h - 6);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const last = points[points.length - 1];
  const first = points[0];
  const tone = last > first ? "text-ok" : last < first ? "text-danger" : "text-muted";
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className={`shrink-0 ${tone}`} aria-hidden>
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
        strokeLinecap="round"
        points={coords}
      />
    </svg>
  );
}
