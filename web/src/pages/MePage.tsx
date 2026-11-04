import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  DISPLAY_NAME,
  WEIGHT_NUDGE_DAYS,
  biggestWeekLift,
  daysSince,
  formatKg,
  insightDetail,
  insightHeadline,
  shortLift,
  weekDoneCount,
} from "../lib/profileView";
import { useSkinStore, type Skin } from "../store/skin";
import type { ExerciseStat, Profile, TrainingSession } from "../types";

const THEMES: { id: Skin; label: string }[] = [
  { id: "lavender", label: "淡紫" },
  { id: "mint", label: "薄荷" },
  { id: "dark", label: "深色" },
];

type WeightPoint = { weight_kg: number; recorded_at: string };

type Props = {
  profile: Profile;
  onUpdated: () => void;
  onLogout: () => void;
};

export function MePage({ profile, onUpdated, onLogout }: Props) {
  const qc = useQueryClient();
  const { skin, setSkin } = useSkinStore();
  const [weightOpen, setWeightOpen] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const letter = DISPLAY_NAME.slice(0, 1);

  const { data: history = [], isLoading: weightLoading } = useQuery({
    queryKey: ["weight-history"],
    queryFn: () => api<WeightPoint[]>("/api/profile/weight-history?limit=8"),
  });
  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=30"),
  });
  const { data: exercises = [], isLoading: liftsLoading } = useQuery({
    queryKey: ["exercises"],
    queryFn: () => api<ExerciseStat[]>("/api/training/exercises"),
  });

  const points = useMemo(() => history.slice(-8), [history]);
  const delta = useMemo(() => {
    if (points.length < 2) return null;
    const last = points[points.length - 1].weight_kg;
    const prev = points[points.length - 2].weight_kg;
    return Math.round((last - prev) * 10) / 10;
  }, [points]);
  const weekCount = useMemo(() => weekDoneCount(sessions), [sessions]);
  const featured = useMemo(() => biggestWeekLift(sessions), [sessions]);
  const pr = useMemo(() => pickPr(exercises, featured?.name), [exercises, featured]);
  const headline = useMemo(() => insightHeadline(sessions, weekCount), [sessions, weekCount]);
  const detail = useMemo(() => insightDetail(profile), [profile]);
  const lastWeightAt = points.length ? points[points.length - 1].recorded_at : null;
  const weightDays = lastWeightAt ? daysSince(lastWeightAt) : null;
  const showWeightTodo = !weightLoading && (points.length === 0 || (weightDays != null && weightDays >= WEIGHT_NUDGE_DAYS));
  const weightDelta = deltaLabel(delta);

  function flash(message: string) {
    setHint(message);
    window.setTimeout(() => setHint(null), 1600);
  }

  return (
    <div className="flex min-h-full flex-col px-page pb-6 pt-3">
      <p className="font-display text-meta font-semibold uppercase tracking-[0.06em] text-muted">
        Gym Coach
      </p>

      <section className="flex items-center gap-3.5 py-4">
        <div className="grid h-16 w-16 shrink-0 place-items-center rounded-xl bg-ink font-display text-display font-semibold text-accent-ink">
          {letter}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-display font-semibold tracking-tight">{DISPLAY_NAME}</h1>
          <p className="mt-0.5 text-label text-muted">
            {profile.goal} · {profile.experience} · 每周 {profile.days_per_week} 练
          </p>
        </div>
        <Link
          to="/me/edit"
          className="pressable shrink-0 rounded-full border border-line bg-elevated px-3 py-1.5 text-label font-semibold"
        >
          编辑
        </Link>
      </section>

      <section className="grid grid-cols-3 gap-2">
        <Stat
          value={sessionsLoading ? "—" : String(weekCount)}
          unit={sessionsLoading ? undefined : "次"}
          label="本周训练"
        />
        <Stat
          value={liftsLoading ? "—" : pr.kg}
          unit={!liftsLoading && pr.kg !== "—" ? "kg" : undefined}
          label={liftsLoading ? "主项 PR" : pr.label}
          dark
        />
        <Stat value={formatKg(profile.weight_kg)} unit="kg" label="当前体重" />
      </section>

      <section className="relative mt-3.5 overflow-hidden rounded-lg bg-ink px-4 py-4 text-accent-ink">
        <div
          className="pointer-events-none absolute -bottom-10 -right-8 h-40 w-40 bg-accent opacity-80"
          style={{ clipPath: "polygon(30% 0, 100% 0, 100% 100%, 0 70%)" }}
          aria-hidden
        />
        <p className="text-micro font-semibold tracking-[0.1em] opacity-65">AI 洞察</p>
        <h2 className="relative mt-2.5 font-display text-title font-semibold leading-snug">{headline}</h2>
        <p className="relative mt-1.5 max-w-[28ch] text-meta leading-relaxed opacity-80">{detail}</p>
        {showWeightTodo && (
          <div className="relative mt-3.5 flex items-center gap-2.5 border-t border-line pt-3 opacity-90">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-elevated/20 text-accent-ink">
              <ScaleIcon />
            </span>
            <p className="min-w-0 flex-1 text-label">
              {points.length === 0 || weightDays == null ? "还没有体重记录" : `上次体重记录是 ${weightDays} 天前`}
            </p>
            <button
              type="button"
              onClick={() => setWeightOpen(true)}
              className="pressable shrink-0 rounded-full bg-accent px-3 py-1.5 text-micro font-semibold text-accent-ink"
            >
              记体重
            </button>
          </div>
        )}
      </section>

      <section className="mt-3.5 rounded-md border border-line bg-elevated p-4">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-label font-semibold text-muted">体重趋势</p>
          {weightDelta && (
            <p className={`text-label font-semibold ${weightDelta.className}`}>{weightDelta.text}</p>
          )}
        </div>
        <p className="num mt-1 text-display font-semibold leading-none">
          {formatKg(profile.weight_kg)}
          <small className="ml-1 text-meta font-medium text-muted">kg</small>
        </p>
        <p className="mt-1.5 text-micro text-muted">
          {points.length > 0 ? `近 ${points.length} 次记录` : "还没有体重记录"}
        </p>
        <WeightSpark values={points.map((point) => point.weight_kg)} />
      </section>

      <button
        type="button"
        onClick={() => flash("即将上线")}
        className="mt-3.5 w-full rounded-md border border-dashed border-line bg-elevated px-4 py-3.5 text-center opacity-50"
      >
        <span className="mt-1 block text-label font-semibold text-muted">营养饮食 · 即将上线</span>
      </button>

      <section className="mt-6">
        <p className="text-micro font-semibold text-muted">外观</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {THEMES.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSkin(item.id)}
              className={`pressable rounded-md px-3 py-2 text-label font-semibold ${
                skin === item.id ? "bg-accent text-accent-ink" : "border border-line bg-elevated"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <button
        type="button"
        onClick={onLogout}
        className="mt-6 text-center text-micro font-semibold text-muted"
      >
        退出登录
      </button>

      {hint && (
        <p className="pointer-events-none fixed bottom-24 left-1/2 z-30 -translate-x-1/2 rounded-full bg-ink px-3 py-1.5 text-xs font-bold text-[var(--bg)]">
          {hint}
        </p>
      )}

      {weightOpen &&
        createPortal(
          <WeightSheet
            current={profile.weight_kg}
            onClose={() => setWeightOpen(false)}
            onSaved={async () => {
              setWeightOpen(false);
              await qc.invalidateQueries({ queryKey: ["weight-history"] });
              onUpdated();
            }}
          />,
          document.body,
        )}
    </div>
  );
}

function pickPr(exercises: ExerciseStat[], featuredName?: string): { label: string; kg: string } {
  const featured = featuredName
    ? exercises.find((item) => item.name === featuredName && item.best_weight != null && item.best_weight > 0)
    : undefined;
  const heaviest = [...exercises]
    .filter((item) => item.best_weight != null && item.best_weight > 0)
    .sort((a, b) => (b.best_weight ?? 0) - (a.best_weight ?? 0))[0];
  const picked = featured ?? heaviest;
  if (!picked || picked.best_weight == null) return { label: "主项 PR", kg: "—" };
  return { label: `${shortLift(picked.name)} PR`, kg: formatKg(picked.best_weight) };
}

function deltaLabel(delta: number | null): { text: string; className: string } | null {
  if (delta == null) return null;
  if (delta === 0) return { text: "较上次持平", className: "text-muted" };
  const down = delta < 0;
  return {
    text: `${down ? "↓" : "↑"} ${formatKg(Math.abs(delta))} kg vs 上次`,
    className: down ? "text-ok" : "text-ink",
  };
}

function Stat({
  value,
  unit,
  label,
  dark,
}: {
  value: string;
  unit?: string;
  label: string;
  dark?: boolean;
}) {
  return (
    <div
      className={`rounded-md border px-2 py-3.5 text-center ${
        dark ? "border-ink bg-ink text-accent-ink" : "border-line bg-elevated"
      }`}
    >
      <p className={`num text-display font-semibold leading-none ${dark ? "text-accent-ink" : ""}`}>
        {value}
        {unit && (
          <small className={`ml-0.5 text-micro font-medium ${dark ? "text-accent-ink opacity-60" : "text-muted"}`}>
            {unit}
          </small>
        )}
      </p>
      <p className={`mt-1.5 text-micro font-semibold ${dark ? "text-accent-ink opacity-60" : "text-muted"}`}>{label}</p>
    </div>
  );
}

function WeightSpark({ values }: { values: number[] }) {
  if (values.length === 0) return null;
  const width = 340;
  const height = 70;
  // 只有 1 条记录时画一条平线 + 末点，避免空白；≥2 条才画真实折线。
  const series = values.length === 1 ? [values[0], values[0]] : values;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const coords = series.map((value, index) => {
    const x = (index / (series.length - 1)) * (width - 20) + 10;
    const y = 12 + (1 - (value - min) / span) * (height - 28);
    return { x, y };
  });
  const first = coords[0];
  const last = coords[coords.length - 1];
  const single = values.length === 1;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="mt-3.5 h-[70px] w-full">
      <line x1="0" y1="18" x2={width} y2="18" stroke="var(--line)" strokeWidth="1" strokeDasharray="3 4" />
      <line x1="0" y1="48" x2={width} y2="48" stroke="var(--line)" strokeWidth="1" strokeDasharray="3 4" />
      <polyline
        points={coords.map((point) => `${point.x},${point.y}`).join(" ")}
        fill="none"
        stroke="var(--ink)"
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={single ? 0.35 : 1}
      />
      <circle cx={last.x} cy={last.y} r="6" fill="var(--accent)" stroke="var(--ink)" strokeWidth="2.5" />
      {!single && <circle cx={first.x} cy={first.y} r="3.5" fill="var(--ink)" />}
    </svg>
  );
}

function ScaleIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20H2" />
    </svg>
  );
}

function WeightSheet({
  current,
  onClose,
  onSaved,
}: {
  current: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [w, setW] = useState(current);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await api("/api/profile/weight", {
        method: "POST",
        body: JSON.stringify({ weight_kg: w }),
      });
      onSaved();
    } catch (error) {
      alert(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-scrim p-0 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-t-2xl border border-line bg-bg px-5 pb-8 pt-5 shadow-xl sm:rounded-2xl">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-extrabold">记一笔体重</h2>
          <button type="button" className="text-sm font-bold text-muted" onClick={onClose}>
            关闭
          </button>
        </div>
        <p className="mt-1 text-xs text-muted">写入趋势，不是改死数字表单。</p>
        <div className="mt-6 flex items-center justify-center gap-4">
          <button
            type="button"
            className="pressable grid h-12 w-12 place-items-center rounded-md border border-line text-xl font-bold"
            onClick={() => setW((x) => Math.max(31, Math.round((x - 0.1) * 10) / 10))}
          >
            −
          </button>
          <div className="text-center">
            <div className="font-display text-4xl font-extrabold">
              <span className="font-num">{w.toFixed(1)}</span>
            </div>
            <div className="text-xs text-muted">kg</div>
          </div>
          <button
            type="button"
            className="pressable grid h-12 w-12 place-items-center rounded-md border border-line text-xl font-bold"
            onClick={() => setW((x) => Math.min(299, Math.round((x + 0.1) * 10) / 10))}
          >
            +
          </button>
        </div>
        <div className="mt-4 flex justify-center gap-2">
          {([-0.5, 0.5, 1] as const).map((step) => (
            <button
              key={step}
              type="button"
              className="rounded-md border border-line px-3 py-1.5 text-xs font-bold"
              onClick={() =>
                setW((x) => Math.min(299, Math.max(31, Math.round((x + step) * 10) / 10)))
              }
            >
              {step > 0 ? `+${step}` : `${step}`}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void save()}
          className="pressable mt-6 w-full rounded-md bg-accent py-3.5 font-display text-base font-extrabold text-accent-ink disabled:opacity-60"
        >
          {busy ? "写入中…" : "确认入账"}
        </button>
      </div>
    </div>
  );
}
