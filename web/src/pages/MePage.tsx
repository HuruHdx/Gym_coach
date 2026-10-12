import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { INJURY_PRESETS } from "../lib/profileOptions";
import type { Profile } from "../types";
import { useSkinStore, type Skin } from "../store/skin";

const SKINS: { id: Skin; label: string }[] = [
  { id: "court", label: "Court 酸柠" },
  { id: "cobalt", label: "Cobalt 钴蓝" },
  { id: "ember", label: "Ember 橙" },
];

type WeightPoint = { weight_kg: number; recorded_at: string };

type Props = {
  profile: Profile;
  onUpdated: () => void;
  onLogout: () => void;
};

export function MePage({ profile, onUpdated, onLogout }: Props) {
  const { skin, setSkin } = useSkinStore();
  const qc = useQueryClient();
  const [weightOpen, setWeightOpen] = useState(false);
  const [injuryOpen, setInjuryOpen] = useState(false);

  const { data: history = [] } = useQuery({
    queryKey: ["weight-history"],
    queryFn: () => api<WeightPoint[]>("/api/profile/weight-history?limit=14"),
  });

  const delta = useMemo(() => {
    if (history.length < 2) return null;
    const last = history[history.length - 1].weight_kg;
    const prev = history[history.length - 2].weight_kg;
    return Math.round((last - prev) * 10) / 10;
  }, [history]);

  const prefs =
    !profile.preferences?.length || profile.preferences.length >= 4
      ? "器械不限"
      : profile.preferences.join(" · ");

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-display text-[11px] font-extrabold uppercase tracking-[0.12em] text-muted">
            Gym Coach
          </p>
          <h1 className="font-display text-[26px] font-bold tracking-tight">我的</h1>
        </div>
        <Link
          to="/me/settings"
          className="pressable mt-1 grid h-10 w-10 place-items-center rounded-md border border-line bg-elevated text-sm font-bold"
          aria-label="训练资料设置"
          title="训练资料"
        >
          ⚙
        </Link>
      </div>

      {/* 身份状态卡 */}
      <section className="relative mt-4 overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-[var(--hero-a)] to-bg px-4 py-4 rise-in">
        <div
          className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rotate-12 bg-accent/70"
          style={{ clipPath: "polygon(30% 0, 100% 0, 100% 100%, 0 70%)" }}
          aria-hidden
        />
        <div className="relative flex items-center gap-3">
          <div className="grid h-14 w-14 place-items-center rounded-[14px] bg-ink font-display text-xl font-extrabold text-accent">
            {profile.goal.slice(0, 1)}
          </div>
          <div className="min-w-0">
            <div className="font-display text-xl font-extrabold tracking-tight">
              {profile.goal}
              <span className="text-muted"> · </span>
              {profile.experience}
            </div>
            <p className="mt-0.5 text-xs text-muted">
              每周 {profile.days_per_week} 练 · 默认 {profile.session_minutes ?? 45} 分
              {profile.height_cm ? ` · ${profile.height_cm}cm` : ""}
            </p>
            <p className="mt-0.5 truncate text-xs text-muted">{prefs}</p>
          </div>
        </div>
        <Link
          to="/me/settings"
          className="relative mt-3 inline-block text-xs font-bold underline underline-offset-2"
        >
          改目标 / 身份 / 默认场地 →
        </Link>
      </section>

      <button
        type="button"
        onClick={() => setWeightOpen(true)}
        className="pressable mt-3 flex w-full items-center justify-between gap-3 rounded-2xl border border-line bg-elevated px-4 py-3.5 text-left"
      >
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted">体重</p>
          <p className="font-num mt-0.5 text-sm font-bold">
            {profile.weight_kg} kg
            {delta != null && (
              <span className="ml-2 font-medium text-muted">
                {delta === 0 ? "较上次持平" : delta > 0 ? `较上次 +${delta} kg` : `较上次 ${delta} kg`}
              </span>
            )}
          </p>
        </div>
        <span className="shrink-0 text-xs font-bold text-muted">记一笔</span>
      </button>

      {/* 伤痛防护盾 */}
      <section className="mt-3 rounded-2xl border border-line bg-elevated px-4 py-4 rise-in rise-in-delay-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-muted">身体防护</p>
            {profile.injuries.length === 0 ? (
              <p className="mt-2 font-display text-base font-bold">当前无伤痛规避</p>
            ) : (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {profile.injuries.map((i) => (
                  <span
                    key={i}
                    className="rounded-md bg-ink px-2.5 py-1 text-xs font-bold text-accent"
                  >
                    规避 {i}
                  </span>
                ))}
              </div>
            )}
            <p className="mt-2 text-xs text-muted">教练排课会自动剔除高风险动作</p>
          </div>
          <button
            type="button"
            onClick={() => setInjuryOpen(true)}
            className="pressable shrink-0 rounded-md border border-line px-3 py-2 text-xs font-bold"
          >
            管理
          </button>
        </div>
      </section>

      <section className="mt-6">
        <p className="text-[11px] font-bold uppercase tracking-widest text-muted">换肤</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {SKINS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setSkin(s.id)}
              className={`pressable rounded-md px-3 py-2 text-xs font-bold ${
                skin === s.id ? "bg-accent text-accent-ink" : "border border-line bg-elevated"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </section>

      <button
        type="button"
        onClick={onLogout}
        className="pressable mt-8 w-full rounded-md border border-line py-3 text-sm font-bold text-muted"
      >
        退出登录
      </button>

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

      {injuryOpen &&
        createPortal(
          <InjurySheet
            injuries={profile.injuries}
            onClose={() => setInjuryOpen(false)}
            onSaved={() => {
              setInjuryOpen(false);
              onUpdated();
            }}
          />,
          document.body,
        )}
    </div>
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
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-4">
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
          {([-0.5, 0.5, 1] as const).map((d) => (
            <button
              key={d}
              type="button"
              className="rounded-md border border-line px-3 py-1.5 text-xs font-bold"
              onClick={() =>
                setW((x) =>
                  Math.min(299, Math.max(31, Math.round((x + d) * 10) / 10)),
                )
              }
            >
              {d > 0 ? `+${d}` : `${d}`}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={save}
          className="pressable mt-6 w-full rounded-md bg-accent py-3.5 font-display text-base font-extrabold text-accent-ink disabled:opacity-60"
        >
          {busy ? "写入中…" : "确认入账"}
        </button>
      </div>
    </div>
  );
}

function InjurySheet({
  injuries,
  onClose,
  onSaved,
}: {
  injuries: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [list, setList] = useState([...injuries]);
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);

  function toggle(tag: string) {
    setList((prev) =>
      prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag],
    );
  }

  async function save() {
    setBusy(true);
    try {
      await api("/api/profile", {
        method: "PATCH",
        body: JSON.stringify({ injuries: list }),
      });
      onSaved();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-t-2xl border border-line bg-bg px-5 pb-8 pt-5 shadow-xl sm:rounded-2xl">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-extrabold">身体防护</h2>
          <button type="button" className="text-sm font-bold text-muted" onClick={onClose}>
            关闭
          </button>
        </div>
        <p className="mt-1 text-xs text-muted">痊愈了就点掉；新伤点上。改完立刻影响下次计划。</p>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {INJURY_PRESETS.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => toggle(tag)}
              className={`rounded-md px-3 py-2 text-xs font-bold ${
                list.includes(tag)
                  ? "bg-ink text-accent"
                  : "border border-line bg-elevated"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            className="flex-1 rounded-md border border-line bg-elevated px-3 py-2 text-sm outline-none"
            placeholder="其他，如左膝术后"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
          />
          <button
            type="button"
            className="rounded-md border border-line px-3 text-sm font-bold"
            onClick={() => {
              const v = custom.trim();
              if (v && !list.includes(v)) setList([...list, v]);
              setCustom("");
            }}
          >
            添加
          </button>
        </div>
        {list.filter((i) => !(INJURY_PRESETS as readonly string[]).includes(i)).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {list
              .filter((i) => !(INJURY_PRESETS as readonly string[]).includes(i))
              .map((i) => (
                <button
                  key={i}
                  type="button"
                  className="rounded-full border border-line px-3 py-1 text-xs font-bold"
                  onClick={() => setList(list.filter((x) => x !== i))}
                >
                  {i} ×
                </button>
              ))}
          </div>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={save}
          className="pressable mt-6 w-full rounded-md bg-accent py-3.5 font-display text-base font-extrabold text-accent-ink disabled:opacity-60"
        >
          {busy ? "保存中…" : "更新防护"}
        </button>
      </div>
    </div>
  );
}
