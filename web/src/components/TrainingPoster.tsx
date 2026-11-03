import { forwardRef, useEffect, useRef, useState } from "react";
import type { SetLog, TrainingSession } from "../types";

export type PosterRecord = { name: string; detail: string };

export type PosterModel = {
  dateLabel: string;
  tag: string;
  title: string;
  accent: string;
  subtitle: string;
  sets: number;
  minutes: number | null;
  records: PosterRecord[];
  streak: number;
  quote: string;
};

const WEEK = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function leadName(session: TrainingSession): string {
  const counts = new Map<string, number>();
  for (const set of session.sets) {
    if (!set.completed) continue;
    const muscle = (set.muscle || "").trim();
    if (!muscle) continue;
    counts.set(muscle, (counts.get(muscle) || 0) + 1);
  }
  let best = "";
  let bestCount = 0;
  for (const [muscle, count] of counts) {
    if (count > bestCount) {
      best = muscle;
      bestCount = count;
    }
  }
  const split = (session.split_label || "").replace(/训$/, "").trim();
  return (best || split || "今天").replace(/部$/, "");
}

function dateLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${month}·${day} ${WEEK[date.getDay()]}`;
}

function isEarlier(a: TrainingSession, b: TrainingSession): boolean {
  if (a.session_date !== b.session_date) return a.session_date < b.session_date;
  return a.id < b.id;
}

type Effort = { weight: number; reps: number; score: number };

function bestEffort(sets: SetLog[], name: string): Effort | null {
  let best: Effort | null = null;
  for (const set of sets) {
    if (!set.completed || set.exercise_name !== name) continue;
    const reps = set.actual_reps ?? 0;
    const weight = set.actual_weight != null && set.actual_weight > 0 ? set.actual_weight : 0;
    const score = weight > 0 && reps > 0 ? weight * (1 + reps / 30) : reps;
    if (score <= 0) continue;
    if (!best || score > best.score) best = { weight, reps, score };
  }
  return best;
}

function num(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

function effortDetail(prev: Effort, current: Effort): string {
  if (prev.weight > 0 && current.weight > 0) {
    return `${num(prev.weight)}kg×${prev.reps} → ${num(current.weight)}kg×${current.reps}`;
  }
  if (current.reps > prev.reps) return `+${current.reps - prev.reps}次`;
  return "新高";
}

function breakthroughs(current: TrainingSession, history: TrainingSession[] | undefined): PosterRecord[] {
  const older = (history || []).filter(
    (item) => item.id !== current.id && item.status === "done" && isEarlier(item, current),
  );
  const names = [...new Set(current.sets.filter((set) => set.completed).map((set) => set.exercise_name))];
  const found: PosterRecord[] = [];
  for (const name of names) {
    const now = bestEffort(current.sets, name);
    if (!now) continue;
    let prev: Effort | null = null;
    for (const item of older) {
      const best = bestEffort(item.sets, name);
      if (best && (!prev || best.score > prev.score)) prev = best;
    }
    if (!prev || now.score <= prev.score) continue;
    found.push({ name, detail: effortDetail(prev, now) });
  }
  return found;
}

function dominantFeeling(session: TrainingSession): string | null {
  const rank: Record<string, number> = { 力竭: 3, 合适: 2, 轻松: 1 };
  let best: string | null = null;
  for (const set of session.sets) {
    if (!set.completed || !set.feeling || !(set.feeling in rank)) continue;
    if (!best || rank[set.feeling] > rank[best]) best = set.feeling;
  }
  return best;
}

function quoteLine(coach: string, summary?: string | null): string {
  const source = coach.trim() || (summary || "").trim();
  if (!source) return "这场按计划做完了。";
  const sentence = source.split(/[。！？\n]/).map((part) => part.trim()).find(Boolean) || source;
  return sentence.length > 28 ? `${sentence.slice(0, 28)}…` : sentence;
}

export function buildPosterModel(
  current: TrainingSession,
  history: TrainingSession[] | undefined,
  streak: number,
  coach: string,
): PosterModel {
  const muscle = leadName(current);
  const records = breakthroughs(current, history);
  const feeling = dominantFeeling(current);
  let title = `${muscle}训练`;
  let accent = "完成";
  let subtitle = "今日计划已执行";
  if (feeling === "力竭") {
    title = `${muscle}练到`;
    accent = "力竭";
    subtitle = records[0] ? `${records[0].name}破纪录，状态在线` : "这组力竭，强度到位";
  } else if (current.session_outcome === "有突破" || records.length > 0) {
    title = `${muscle}练出`;
    accent = "突破";
    subtitle = records[0] ? `${records[0].name}破纪录` : "今天有进步";
  } else if (current.session_outcome === "偏吃力") {
    title = `${muscle}今天`;
    accent = "吃力";
    subtitle = "重量偏大，下次可微调";
  }
  const tagName = (current.split_label || muscle).replace(/训$/, "").trim() || muscle;
  return {
    dateLabel: dateLabel(current.session_date),
    tag: `${tagName} · ${current.status === "done" ? "已完成" : "进行中"}`,
    title,
    accent,
    subtitle,
    sets: current.sets.filter((set) => set.completed).length,
    minutes: current.duration_minutes != null && current.duration_minutes >= 1 ? current.duration_minutes : null,
    records,
    streak,
    quote: quoteLine(coach, current.summary),
  };
}

export const TrainingPoster = forwardRef<HTMLDivElement, { model: PosterModel }>(function TrainingPoster(
  { model },
  ref,
) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const apply = () => setScale(frame.clientWidth / 360);
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);

  const shown = model.records.slice(0, 2);

  return (
    <div ref={frameRef} style={{ width: "100%", maxWidth: 360, height: 480 * scale, margin: "0 auto" }}>
      <div style={{ width: 360, height: 480, transform: `scale(${scale})`, transformOrigin: "top left" }}>
        <div
          ref={ref}
          data-theme="dark"
          style={{
            width: 360,
            height: 480,
            borderRadius: "var(--r-xl)",
            overflow: "hidden",
            position: "relative",
            color: "var(--text-1)",
            display: "flex",
            flexDirection: "column",
            background: "var(--bg)",
            fontFamily: "var(--font-sans)",
          }}
        >
          <div
            style={{
              position: "relative",
              zIndex: 2,
              flex: 1,
              display: "flex",
              flexDirection: "column",
              padding: "26px 24px 22px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "var(--fs-micro)", fontWeight: 600, letterSpacing: "0.2em", color: "var(--accent-text)" }}>
                GYM COACH
              </span>
              <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-3)" }}>{model.dateLabel}</span>
            </div>

            <div
              style={{
                marginTop: 20,
                display: "inline-flex",
                alignSelf: "flex-start",
                alignItems: "center",
                gap: 6,
                background: "var(--accent-soft)",
                border: "var(--hairline) solid var(--line-strong)",
                borderRadius: 999,
                padding: "4px 12px",
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: "var(--accent)",
                }}
              />
              <span style={{ fontSize: "var(--fs-micro)", fontWeight: 600, color: "var(--accent-text)" }}>{model.tag}</span>
            </div>

            <div
              style={{
                marginTop: 14,
                fontSize: "var(--fs-display)",
                fontWeight: 600,
                letterSpacing: "-0.02em",
                lineHeight: 1.2,
              }}
            >
              {model.title}
              <em style={{ fontStyle: "italic", color: "var(--warn)" }}>{model.accent}</em>
            </div>
            <div style={{ marginTop: 6, fontSize: "var(--fs-meta)", color: "var(--text-3)" }}>{model.subtitle}</div>

            <div style={{ marginTop: "auto", display: "flex", gap: 10 }}>
              <Stat value={String(model.sets)} label="完成组数" />
              <Stat value={model.minutes != null ? String(model.minutes) : "—"} label="训练分钟" tone="accent" />
              <Stat value={String(model.records.length)} label="破纪录" tone="warn" />
            </div>

            <div
              style={{
                marginTop: 14,
                background: "var(--surface)",
                border: "var(--hairline) solid var(--line)",
                borderRadius: "var(--r-lg)",
                padding: "13px 15px",
              }}
            >
              <div style={{ fontSize: "var(--fs-micro)", color: "var(--text-3)", letterSpacing: "0.08em" }}>今日突破</div>
              <div style={{ marginTop: 9, display: "flex", flexDirection: "column", gap: 7 }}>
                {shown.length === 0 ? (
                  <div style={{ fontSize: "var(--fs-meta)", color: "var(--text-3)" }}>今天没有打破以往纪录</div>
                ) : (
                  shown.map((item) => (
                    <div
                      key={item.name}
                      style={{ display: "flex", alignItems: "center", gap: 9, fontSize: "var(--fs-meta)", fontWeight: 600 }}
                    >
                      <span
                        style={{
                          fontSize: "var(--fs-micro)",
                          fontWeight: 600,
                          letterSpacing: "0.06em",
                          color: "var(--accent-ink)",
                          background: "var(--accent)",
                          borderRadius: "var(--r-sm)",
                          padding: "2px 7px",
                        }}
                      >
                        PR
                      </span>
                      <span style={{ color: "var(--text-1)" }}>{item.name}</span>
                      <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-3)", fontWeight: 400 }}>{item.detail}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div
              style={{
                marginTop: 14,
                display: "flex",
                alignItems: "center",
                gap: 9,
                fontSize: "var(--fs-meta)",
                color: "var(--text-2)",
              }}
            >
              已连续打卡 <b style={{ color: "var(--warn)", fontSize: "var(--fs-body)" }}>{model.streak}</b> 天
            </div>

            <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: "var(--fs-label)", color: "var(--text-2)", lineHeight: 1.5 }}>“{model.quote}”</span>
              <span
                style={{
                  flexShrink: 0,
                  fontSize: "var(--fs-micro)",
                  letterSpacing: "0.18em",
                  color: "var(--text-3)",
                  fontWeight: 600,
                }}
              >
                GYM COACH
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

function Stat({ value, label, tone }: { value: string; label: string; tone?: "accent" | "warn" }) {
  const color = tone === "warn" ? "var(--warn)" : tone === "accent" ? "var(--accent-text)" : "var(--text-1)";
  return (
    <div
      style={{
        flex: 1,
        background: "var(--surface)",
        border: "var(--hairline) solid var(--line)",
        borderRadius: "var(--r-xl)",
        padding: "14px 8px",
        textAlign: "center",
      }}
    >
      <div className="num" style={{ fontSize: "var(--fs-display)", fontWeight: 600, lineHeight: 1, color }}>
        {value}
      </div>
      <div style={{ marginTop: 6, fontSize: "var(--fs-micro)", color: "var(--text-3)" }}>{label}</div>
    </div>
  );
}
