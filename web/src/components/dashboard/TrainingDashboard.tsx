import type {
  KeyLift,
  MusclePulse,
  SessionCompare,
  TrainingDashboard as DashboardData,
  WeekRhythm,
} from "../../types";

type Props = {
  data: DashboardData;
  onOpenSession?: (sessionId: number) => void;
  onOpenExercise?: (name: string) => void;
};

export function TrainingDashboard({ data, onOpenSession, onOpenExercise }: Props) {
  return (
    <div className="space-y-3 rise-in">
      <header className="px-0.5">
        <p className="text-[11px] font-bold uppercase tracking-widest text-muted">战报</p>
        <p className="font-display mt-1 text-[15px] font-bold leading-snug tracking-tight text-ink">
          {data.headline}
        </p>
      </header>

      <WeekStrip
        week={data.week}
        onDayClick={(id) => onOpenSession?.(id)}
      />

      {data.session_compare && (
        <SessionCompareBlock
          cmp={data.session_compare}
          onOpenSession={onOpenSession}
          onOpenExercise={onOpenExercise}
        />
      )}

      <MusclePulseBlock
        rows={data.muscle_pulse}
        onOpenSession={onOpenSession}
      />

      {data.key_lifts.length > 0 && (
        <KeyLiftsBlock
          lifts={data.key_lifts}
          onOpenExercise={onOpenExercise}
        />
      )}
    </div>
  );
}

function WeekStrip({
  week,
  onDayClick,
}: {
  week: WeekRhythm;
  onDayClick?: (sessionId: number) => void;
}) {
  return (
    <section className="rounded-2xl border border-line bg-elevated px-3.5 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[11px] font-bold text-muted">本周节奏</p>
        <p className="font-num text-xs font-bold text-ink">
          {week.trained_days}
          <span className="text-muted"> / {week.target_days} 天</span>
        </p>
      </div>
      <div className="mt-3 grid grid-cols-7">
        {week.days.map((d) => {
          const clickable = Boolean(d.session_id && onDayClick);
          const Tag = clickable ? "button" : "div";
          const dayNum = Number(d.date.slice(8));
          return (
            <Tag
              key={d.date}
              type={clickable ? "button" : undefined}
              onClick={
                clickable && d.session_id
                  ? () => onDayClick?.(d.session_id!)
                  : undefined
              }
              className={`flex flex-col items-center gap-1.5 py-1 ${
                clickable ? "pressable" : ""
              }`}
            >
              <span className="text-[11px] font-medium text-muted">{d.label}</span>
              <span
                className={`grid h-8 w-8 place-items-center rounded-full font-num text-[13px] font-bold ${
                  d.is_today
                    ? "bg-ink text-bg"
                    : d.trained
                      ? "text-ink"
                      : "text-muted"
                }`}
              >
                {d.is_today ? "今" : dayNum}
              </span>
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  d.trained ? "bg-ink" : "bg-transparent"
                }`}
              />
            </Tag>
          );
        })}
      </div>
    </section>
  );
}

function SessionCompareBlock({
  cmp,
  onOpenSession,
  onOpenExercise,
}: {
  cmp: SessionCompare;
  onOpenSession?: (id: number) => void;
  onOpenExercise?: (name: string) => void;
}) {
  const title = cmp.muscle || cmp.split_label || "训练";
  return (
    <section className="rounded-2xl border border-line bg-elevated px-3.5 py-3.5">
      <button
        type="button"
        disabled={!onOpenSession}
        onClick={() => onOpenSession?.(cmp.session_id)}
        className={`flex w-full items-start justify-between gap-2 text-left ${
          onOpenSession ? "pressable" : ""
        }`}
      >
        <div>
          <p className="text-[11px] font-bold text-muted">最近一战 · 同部位对比</p>
          <p className="font-display mt-0.5 text-base font-extrabold tracking-tight">
            {title}
            <span className="ml-1.5 text-sm font-bold text-muted">
              {cmp.session_date.slice(5)}
            </span>
          </p>
          <p className="mt-0.5 text-[11px] text-muted">
            {cmp.quality}
            {cmp.done_sets > 0 ? ` · ${cmp.done_sets}/${cmp.total_sets} 组` : ""}
            {cmp.duration_minutes != null ? ` · ${cmp.duration_minutes} 分钟` : ""}
            {cmp.prev_date
              ? ` · vs ${cmp.prev_date.slice(5)}`
              : " · 尚无同部位上场次"}
          </p>
        </div>
        {onOpenSession && (
          <span className="shrink-0 pt-1 text-[11px] font-bold text-muted">详情 →</span>
        )}
      </button>

      <ul className="mt-3 divide-y divide-line/80">
        {cmp.lifts.map((lift) => (
          <li key={lift.exercise_name}>
            <button
              type="button"
              disabled={!onOpenExercise}
              onClick={() => onOpenExercise?.(lift.exercise_name)}
              className={`flex w-full items-center justify-between gap-2 py-2.5 text-left ${
                onOpenExercise ? "pressable" : ""
              }`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-bold">{lift.exercise_name}</p>
                <p className="font-num mt-0.5 text-[11px] text-muted">{lift.load}</p>
              </div>
              <DeltaPill kind={lift.delta_kind} label={lift.delta_label} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function MusclePulseBlock({
  rows,
  onOpenSession,
}: {
  rows: MusclePulse[];
  onOpenSession?: (id: number) => void;
}) {
  const shown = rows.filter((r) => r.status !== "idle" || r.count_30d > 0);
  if (shown.length === 0) return null;

  return (
    <section className="rounded-2xl border border-line bg-elevated px-3.5 py-3.5">
      <p className="text-[11px] font-bold text-muted">部位节拍 · 近 30 天</p>
      <ul className="mt-2 space-y-1">
        {shown.map((r) => {
          const clickable = Boolean(r.last_session_id && onOpenSession);
          const Tag = clickable ? "button" : "div";
          return (
            <Tag
              key={r.muscle}
              type={clickable ? "button" : undefined}
              onClick={
                clickable && r.last_session_id
                  ? () => onOpenSession?.(r.last_session_id!)
                  : undefined
              }
              className={`flex w-full items-center justify-between gap-2 rounded-lg px-1 py-1.5 text-left ${
                clickable ? "pressable hover:bg-bg/80" : ""
              }`}
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="w-6 text-sm font-bold">{r.muscle}</span>
                <span className="text-[11px] text-muted">
                  {r.days_since == null
                    ? "未练过"
                    : r.days_since === 0
                      ? "今天"
                      : r.days_since === 1
                        ? "昨天"
                        : `${r.days_since} 天前`}
                  <span className="mx-1 text-line">·</span>
                  {r.count_30d} 次
                </span>
              </div>
              <span
                className={`shrink-0 text-[11px] font-bold ${
                  r.status === "overdue"
                    ? "text-danger"
                    : r.trend === "↑"
                      ? "text-ok"
                      : "text-muted"
                }`}
              >
                {r.status === "overdue"
                  ? "缺练"
                  : r.trend === "↑"
                    ? "↑"
                    : r.trend === "↓"
                      ? "↓"
                      : "→"}
              </span>
            </Tag>
          );
        })}
      </ul>
    </section>
  );
}

function KeyLiftsBlock({
  lifts,
  onOpenExercise,
}: {
  lifts: KeyLift[];
  onOpenExercise?: (name: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-line bg-elevated px-3.5 py-3.5">
      <p className="text-[11px] font-bold text-muted">主力进阶</p>
      <ul className="mt-2 divide-y divide-line/80">
        {lifts.map((lift) => (
          <li key={lift.exercise_name}>
            <button
              type="button"
              disabled={!onOpenExercise}
              onClick={() => onOpenExercise?.(lift.exercise_name)}
              className={`flex w-full items-center justify-between gap-2 py-2.5 text-left ${
                onOpenExercise ? "pressable" : ""
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="truncate text-sm font-bold">{lift.exercise_name}</p>
                  {lift.is_pr && (
                    <span className="rounded bg-ink px-1 py-0.5 text-[9px] font-extrabold text-accent">
                      PR
                    </span>
                  )}
                </div>
                <p className="font-num mt-0.5 text-[11px] text-muted">
                  {lift.load}
                  {lift.muscle ? ` · ${lift.muscle}` : ""}
                </p>
              </div>
              <span
                className={`shrink-0 text-right text-[11px] font-bold ${
                  lift.delta_kg > 0.01
                    ? "text-ok"
                    : lift.delta_kg < -0.01
                      ? "text-danger"
                      : "text-muted"
                }`}
              >
                {lift.delta_label.replace("较30天前 ", "")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DeltaPill({ kind, label }: { kind: string; label: string }) {
  const color =
    kind === "up"
      ? "text-ok"
      : kind === "down"
        ? "text-danger"
        : kind === "new"
          ? "text-ink"
          : "text-muted";
  return (
    <span className={`font-num shrink-0 text-[12px] font-extrabold ${color}`}>{label}</span>
  );
}
