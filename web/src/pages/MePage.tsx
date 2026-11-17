import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, fetchFollowing } from "../lib/api";
import {
  daysSince,
  displayNameOf,
  formatKg,
  type AuthUser,
} from "../lib/profileView";
import { DEFAULT_EQUIPMENT, EQUIPMENT_OPTIONS } from "../lib/profileOptions";
import { useSkinStore, type Skin } from "../store/skin";
import type { Profile, TrainingSession } from "../types";

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

export function MePage({ profile, onLogout }: Props) {
  const { skin, setSkin } = useSkinStore();
  const [logoutAsk, setLogoutAsk] = useState(false);

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<AuthUser>("/api/auth/me"),
  });
  const name = displayNameOf(me);
  const letter = name.slice(0, 1);

  const { data: history = [] } = useQuery({
    queryKey: ["weight-history", me?.id],
    queryFn: () => api<WeightPoint[]>("/api/profile/weight-history?limit=8"),
    enabled: Boolean(me?.id),
  });
  const { data: sessions = [] } = useQuery({
    queryKey: ["training-sessions", me?.id],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=60"),
    enabled: Boolean(me?.id),
  });
  const { data: following } = useQuery({
    queryKey: ["plans-following"],
    queryFn: fetchFollowing,
  });

  const points = useMemo(() => history.slice(-8), [history]);
  const delta = useMemo(() => {
    if (points.length < 2) return null;
    const last = points[points.length - 1].weight_kg;
    const prev = points[points.length - 2].weight_kg;
    return Math.round((last - prev) * 10) / 10;
  }, [points]);
  const lastWeightAt = points.length ? points[points.length - 1].recorded_at : null;
  const weightDays = lastWeightAt ? daysSince(lastWeightAt) : null;
  const monthsTraining = useMemo(() => monthsSinceFirst(sessions), [sessions]);
  const equipment = useMemo(() => {
    const prefs = profile.preferences || [];
    return prefs.length ? prefs : [...DEFAULT_EQUIPMENT];
  }, [profile.preferences]);

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3">
      <p className="font-display text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
        Gym Coach
      </p>

      {/* 头部方案 B：浅紫渐变卡 */}
      <Link
        to="/me/settings"
        className="pressable mt-3 flex items-center gap-3 rounded-2xl border border-line bg-gradient-to-br from-[var(--hero-a)] via-elevated to-elevated px-3.5 py-3.5"
      >
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full border border-line bg-elevated text-base font-semibold text-accent-text">
          {letter}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-semibold tracking-tight text-ink">{name}</h1>
          <p className="mt-0.5 text-[11px] text-muted">
            {monthsTraining != null ? `训练第 ${monthsTraining} 个月 · ` : ""}
            每周 {profile.days_per_week} 练
          </p>
        </div>
        <span className="text-lg text-muted" aria-hidden>
          ›
        </span>
      </Link>

      {/* 我的计划 */}
      <section className="mt-3.5 rounded-xl border border-line bg-elevated p-3.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-bold text-muted">我的计划</p>
          {following?.active_plan_id ? (
            <Link
              to={`/plans/${encodeURIComponent(following.active_plan_id)}`}
              className="text-[11px] font-bold text-accent-text"
            >
              管理 ›
            </Link>
          ) : null}
        </div>
        {following?.active_plan_id && following.plan ? (
          <>
            <h2 className="mt-2 text-base font-bold">{following.plan.title}</h2>
            <p className="mt-1 text-[12px] text-muted">
              {following.week.progress_label ||
                `已练 ${following.week.completed_count}/${following.week.total_blocks} 板块`}
              {" · "}
              每周 {following.plan.days_per_week} 练
            </p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <FollowingBlockChips following={following} />
            </div>
          </>
        ) : (
          <Link to="/plans" className="mt-2 block text-sm font-bold text-accent-text">
            还没有在跟的计划 · 去挑一套 ›
          </Link>
        )}
      </section>

      {/* 身体只读 */}
      <Link
        to="/me/settings"
        className="pressable mt-3.5 block rounded-xl border border-line bg-elevated p-3.5"
      >
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-bold text-muted">身体</p>
          <span className="text-[11px] font-bold text-accent-text">改在资料页 ›</span>
        </div>
        <p className="num mt-2 text-2xl font-semibold leading-none">
          {formatKg(profile.weight_kg)}
          {profile.weight_kg != null && (
            <small className="ml-1 text-[12px] font-medium text-muted">kg</small>
          )}
          {delta != null && delta !== 0 && (
            <span className="ml-2 text-[12px] font-semibold text-muted">
              {delta > 0 ? "↑" : "↓"} {formatKg(Math.abs(delta))}
            </span>
          )}
        </p>
        <WeightSpark values={points.map((p) => p.weight_kg)} />
        <p className="mt-2 text-[11px] text-muted">
          目标 {profile.goal}
          {profile.height_cm != null ? ` · 身高 ${profile.height_cm} cm` : ""}
          {weightDays != null ? ` · 上次记录 ${weightDays} 天前` : " · 还没有体重记录"}
        </p>
      </Link>

      {/* 训练条件只读 */}
      <Link
        to="/me/settings"
        className="pressable mt-3.5 block rounded-xl border border-line bg-elevated p-3.5"
      >
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-bold text-muted">训练条件</p>
          <span className="text-[11px] font-bold text-accent-text">修改 ›</span>
        </div>
        <p className="mt-1 text-[11px] text-muted">排课只从这里挑动作</p>
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {EQUIPMENT_OPTIONS.map((opt) => {
            const on = equipment.includes(opt.value);
            return (
              <span
                key={opt.value}
                className={`rounded-md px-2.5 py-1 text-[11px] font-bold ${
                  on ? "bg-tint text-accent-text" : "border border-line text-muted"
                }`}
              >
                {opt.value}
              </span>
            );
          })}
        </div>
      </Link>

      {/* 设置列表 */}
      <section className="mt-4 overflow-hidden rounded-xl border border-line bg-elevated">
        <div className="border-b border-line px-3.5 py-3">
          <p className="text-[11px] font-bold text-muted">外观</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {THEMES.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSkin(item.id)}
                className={`pressable rounded-md px-3 py-1.5 text-[12px] font-semibold ${
                  skin === item.id ? "bg-accent text-accent-ink" : "border border-line bg-bg"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <Link
          to="/exercises"
          className="pressable flex items-center justify-between border-b border-line px-3.5 py-3.5 text-sm font-bold"
        >
          动作库
          <span className="text-muted">›</span>
        </Link>
        {!logoutAsk ? (
          <button
            type="button"
            onClick={() => setLogoutAsk(true)}
            className="pressable w-full px-3.5 py-3.5 text-left text-sm font-bold text-danger"
          >
            退出登录
          </button>
        ) : (
          <div className="flex items-center gap-2 px-3.5 py-3">
            <p className="flex-1 text-[12px] text-muted">确定退出？</p>
            <button
              type="button"
              className="rounded-md border border-line px-3 py-1.5 text-[12px] font-bold"
              onClick={() => setLogoutAsk(false)}
            >
              取消
            </button>
            <button
              type="button"
              className="rounded-md bg-danger px-3 py-1.5 text-[12px] font-bold text-white"
              onClick={onLogout}
            >
              退出
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

function FollowingBlockChips({
  following,
}: {
  following: NonNullable<Awaited<ReturnType<typeof fetchFollowing>>>;
}) {
  const { data: detail } = useQuery({
    queryKey: ["plan-detail", following.active_plan_id],
    queryFn: () =>
      api<import("../types").PlanDetail>(
        `/api/plans/${encodeURIComponent(following.active_plan_id!)}`,
      ),
    enabled: Boolean(following.active_plan_id),
  });
  const blocks = detail?.blocks ?? [];
  const done = new Set(following.week.completed_block_ids || []);
  const nextId = following.week.next_block?.id;
  if (!blocks.length) return null;
  return (
    <>
      {blocks.map((b) => {
        const isNext = b.id === nextId;
        const isDone = done.has(b.id);
        return (
          <span
            key={b.id}
            className={`rounded-md px-2.5 py-1 text-[11px] font-bold ${
              isNext
                ? "bg-tint text-accent-text"
                : isDone
                  ? "border border-line text-muted"
                  : "border border-line bg-bg text-ink"
            }`}
          >
            {b.title}
            {isDone ? " ✓" : ""}
          </span>
        );
      })}
    </>
  );
}

function monthsSinceFirst(sessions: TrainingSession[]): number | null {
  const dates = sessions
    .filter((s) => s.status === "done" || s.status === "active")
    .map((s) => s.session_date)
    .filter(Boolean)
    .sort();
  if (!dates.length) return null;
  const first = new Date(`${dates[0]}T00:00:00`);
  const now = new Date();
  const months =
    (now.getFullYear() - first.getFullYear()) * 12 + (now.getMonth() - first.getMonth()) + 1;
  return Math.max(1, months);
}

function WeightSpark({ values }: { values: number[] }) {
  if (values.length === 0) return null;
  const width = 340;
  const height = 40;
  const series = values.length === 1 ? [values[0], values[0]] : values;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const coords = series.map((value, index) => {
    const x = (index / (series.length - 1)) * (width - 16) + 8;
    const y = 8 + (1 - (value - min) / span) * (height - 16);
    return { x, y };
  });
  const last = coords[coords.length - 1];
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="mt-2 h-10 w-full">
      <polyline
        points={coords.map((p) => `${p.x},${p.y}`).join(" ")}
        fill="none"
        stroke="var(--ink)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={last.x} cy={last.y} r="4" fill="var(--accent)" stroke="var(--ink)" strokeWidth="1.5" />
    </svg>
  );
}
