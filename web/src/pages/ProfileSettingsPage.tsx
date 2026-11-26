import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createPortal } from "react-dom";
import { api } from "../lib/api";
import {
  DEFAULT_EQUIPMENT,
  EQUIPMENT_OPTIONS,
  EXPERIENCES,
  GOALS,
  SESSION_MINUTE_OPTIONS,
  type EquipmentTag,
} from "../lib/profileOptions";
import type { Profile } from "../types";
import { feedbackError, toast } from "../feedback";
import {
  isTestFeedbackEnabled,
  setTestFeedbackEnabled,
} from "../lib/testFeedback";

type Props = { profile: Profile; onUpdated: () => void; onResetOnboarding: () => void };

function currentEquipment(profile: Profile): string[] {
  const prefs = profile.preferences || [];
  return prefs.length ? prefs : [...DEFAULT_EQUIPMENT];
}

/** 训练资料：分组卡 + 画像摘要（方案 A） */
export function ProfileSettingsPage({ profile, onUpdated, onResetOnboarding }: Props) {
  const [busy, setBusy] = useState(false);
  const [rhythmOpen, setRhythmOpen] = useState(false);
  const [heightOpen, setHeightOpen] = useState(false);
  const [weightOpen, setWeightOpen] = useState(false);
  const [heightDraft, setHeightDraft] = useState(String(profile.height_cm ?? ""));
  const [weightDraft, setWeightDraft] = useState(profile.weight_kg ?? 70);
  const [daysDraft, setDaysDraft] = useState(profile.days_per_week);
  const [minutesDraft, setMinutesDraft] = useState(profile.session_minutes ?? 60);
  const [testFeedbackOn, setTestFeedbackOn] = useState(() => isTestFeedbackEnabled());
  const equipment = currentEquipment(profile);

  useEffect(() => {
    setHeightDraft(String(profile.height_cm ?? ""));
    setWeightDraft(profile.weight_kg ?? 70);
    setDaysDraft(profile.days_per_week);
    setMinutesDraft(profile.session_minutes ?? 60);
  }, [profile.height_cm, profile.weight_kg, profile.days_per_week, profile.session_minutes]);

  async function patch(body: Record<string, unknown>, label?: string) {
    setBusy(true);
    try {
      await api("/api/profile", { method: "PATCH", body: JSON.stringify(body) });
      onUpdated();
      if (label) toast.ok(label);
    } catch (e) {
      toast.err(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleEquipment(tag: EquipmentTag) {
    const cur = currentEquipment(profile);
    let next = cur.includes(tag) ? cur.filter((x) => x !== tag) : [...cur, tag];
    if (next.length === 0) next = [...DEFAULT_EQUIPMENT];
    void patch({ preferences: next }, "器械已更新");
  }

  return (
    <div className="flex min-h-full flex-col px-4 pb-8 pt-3">
      <Link to="/me" className="pressable -ml-1 mb-1 inline-flex w-fit text-[12px] font-bold text-muted">
        ‹ 我的
      </Link>
      <h1 className="font-display text-[26px] font-bold tracking-tight">训练资料</h1>

      <section className="mt-4 rounded-xl border border-line bg-tint/40 px-3.5 py-3">
        <p className="text-[11px] font-bold text-muted">你的画像</p>
        <p className="mt-1 text-sm font-bold">
          {profile.experience} · {profile.goal} · 每周 {profile.days_per_week} 练
        </p>
        <p className="mt-1 text-[11px] text-muted">排课会按这套画像挑动作和容量</p>
      </section>

      <section className="mt-3 rounded-xl border border-line bg-elevated p-3.5">
        <p className="text-[11px] font-bold text-muted">身体</p>
        <div className="mt-2 flex items-center justify-between gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => setHeightOpen(true)}
            className="pressable text-left"
          >
            <p className="text-[12px] text-muted">身高</p>
            <p className="num mt-0.5 text-base font-bold">
              {profile.height_cm != null ? `${profile.height_cm} cm` : "未填"}{" "}
              <span className="text-[11px] font-bold text-accent-text">修改 ›</span>
            </p>
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setWeightOpen(true)}
            className="pressable text-right"
          >
            <p className="text-[12px] text-muted">体重</p>
            <p className="num mt-0.5 text-base font-bold">
              {profile.weight_kg != null ? `${profile.weight_kg} kg` : "未填"}{" "}
              <span className="text-[11px] font-bold text-accent-text">记体重 ›</span>
            </p>
          </button>
        </div>
      </section>

      <section className="mt-3">
        <p className="mb-2 text-[11px] font-bold text-muted">目标</p>
        <div className="grid grid-cols-2 gap-2">
          {GOALS.map((g) => {
            const on = profile.goal === g.value;
            return (
              <button
                key={g.value}
                type="button"
                disabled={busy}
                onClick={() => void patch({ goal: g.value }, "目标已更新")}
                className={`pressable relative rounded-xl border px-3 py-3 text-left disabled:opacity-50 ${
                  on ? "border-transparent bg-tint" : "border-line bg-elevated"
                }`}
              >
                {on && (
                  <span className="absolute right-2 top-2 text-[11px] font-bold text-accent-text">✓</span>
                )}
                <p className={`text-sm font-bold ${on ? "text-accent-text" : "text-ink"}`}>{g.value}</p>
                <p className="mt-1 text-[11px] text-muted">{g.sub}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="mt-4">
        <p className="mb-2 text-[11px] font-bold text-muted">身份</p>
        <div className="grid gap-2">
          {EXPERIENCES.map((e) => {
            const on = profile.experience === e.value;
            return (
              <button
                key={e.value}
                type="button"
                disabled={busy}
                onClick={() => void patch({ experience: e.value }, "身份已更新")}
                className={`pressable relative rounded-xl border px-3 py-3 text-left disabled:opacity-50 ${
                  on ? "border-transparent bg-tint" : "border-line bg-elevated"
                }`}
              >
                {on && (
                  <span className="absolute right-2 top-2 text-[11px] font-bold text-accent-text">✓</span>
                )}
                <p className={`text-sm font-bold ${on ? "text-accent-text" : "text-ink"}`}>{e.value}</p>
                <p className="mt-0.5 text-[11px] text-muted">{e.sub}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section className="mt-4 rounded-xl border border-line bg-elevated px-3.5 py-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold text-muted">节奏</p>
            <p className="mt-1 text-sm font-bold">
              每周 {profile.days_per_week} 天 · 每次 {profile.session_minutes ?? 60} 分钟
            </p>
          </div>
          <button
            type="button"
            className="text-[12px] font-bold text-accent-text"
            onClick={() => setRhythmOpen(true)}
          >
            修改 ›
          </button>
        </div>
      </section>

      <section className="mt-4 rounded-xl border border-line bg-elevated p-3.5">
        <p className="text-[11px] font-bold text-muted">场地与器械</p>
        <p className="mt-1 text-[11px] text-muted">开关 = 我有 / 我没有</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {EQUIPMENT_OPTIONS.map((e) => {
            const on = equipment.includes(e.value);
            return (
              <button
                key={e.value}
                type="button"
                disabled={busy}
                onClick={() => toggleEquipment(e.value)}
                className={`pressable flex items-center justify-between rounded-xl border px-3 py-3 text-left disabled:opacity-50 ${
                  on ? "border-transparent bg-tint" : "border-line bg-bg"
                }`}
              >
                <span className={`text-[13px] font-bold ${on ? "text-accent-text" : "text-ink"}`}>
                  {e.value}
                </span>
                <span
                  className={`h-2.5 w-2.5 rounded-full ${on ? "bg-accent" : "border border-line bg-elevated"}`}
                  aria-hidden
                />
              </button>
            );
          })}
        </div>
      </section>

      <section className="mt-6 rounded-xl border border-line bg-elevated p-3.5">
        <p className="text-[11px] font-bold text-muted">开发者</p>
        <div className="mt-2 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-bold">测试反馈</p>
            <p className="mt-0.5 text-[11px] text-muted">开启后教练气泡可点赞踩，并显示轨迹号</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={testFeedbackOn}
            className={`pressable relative h-7 w-12 shrink-0 rounded-full transition-colors ${
              testFeedbackOn ? "bg-accent" : "bg-line"
            }`}
            onClick={() => {
              const next = !testFeedbackOn;
              setTestFeedbackEnabled(next);
              setTestFeedbackOn(next);
              toast.ok(next ? "已开启测试反馈" : "已关闭测试反馈");
            }}
          >
            <span
              className={`absolute top-0.5 h-6 w-6 rounded-full bg-elevated shadow transition-transform ${
                testFeedbackOn ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </button>
        </div>
      </section>

      <button
        type="button"
        className="mt-8 text-center text-sm font-bold text-danger"
        onClick={async () => {
          if (!confirm("清除画像并重新走引导？")) return;
          try {
            await api("/api/profile", { method: "DELETE" });
            onResetOnboarding();
          } catch (e) {
            toast.err(feedbackError(e));
          }
        }}
      >
        重新建画像
      </button>

      {heightOpen &&
        createPortal(
          <Sheet onClose={() => setHeightOpen(false)} title="修改身高">
            <input
              type="number"
              inputMode="decimal"
              className="mt-3 w-full rounded-lg border border-line bg-bg px-3 py-3 text-[16px] font-bold outline-none"
              value={heightDraft}
              placeholder="例如 172"
              onChange={(e) => setHeightDraft(e.target.value)}
            />
            <button
              type="button"
              disabled={busy}
              className="pressable mt-4 w-full rounded-md bg-accent py-3 text-sm font-extrabold text-accent-ink disabled:opacity-50"
              onClick={() => {
                const n = Number(heightDraft);
                const height_cm = !heightDraft || !Number.isFinite(n) || n <= 0 ? null : n;
                void patch({ height_cm }, "身高已更新").then(() => setHeightOpen(false));
              }}
            >
              保存
            </button>
          </Sheet>,
          document.body,
        )}

      {weightOpen &&
        createPortal(
          <Sheet onClose={() => setWeightOpen(false)} title="记一笔体重">
            <div className="mt-4 flex items-center justify-center gap-4">
              <button
                type="button"
                className="pressable grid h-12 w-12 place-items-center rounded-md border border-line text-xl font-bold"
                onClick={() =>
                  setWeightDraft((x) => Math.max(31, Math.round((x - 0.1) * 10) / 10))
                }
              >
                −
              </button>
              <div className="text-center">
                <p className="font-display text-4xl font-extrabold num">{weightDraft.toFixed(1)}</p>
                <p className="text-xs text-muted">kg</p>
              </div>
              <button
                type="button"
                className="pressable grid h-12 w-12 place-items-center rounded-md border border-line text-xl font-bold"
                onClick={() =>
                  setWeightDraft((x) => Math.min(299, Math.round((x + 0.1) * 10) / 10))
                }
              >
                +
              </button>
            </div>
            <button
              type="button"
              disabled={busy}
              className="pressable mt-4 w-full rounded-md bg-accent py-3 text-sm font-extrabold text-accent-ink disabled:opacity-50"
              onClick={async () => {
                setBusy(true);
                try {
                  await api("/api/profile/weight", {
                    method: "POST",
                    body: JSON.stringify({ weight_kg: weightDraft }),
                  });
                  onUpdated();
                  toast.ok("体重已记录");
                  setWeightOpen(false);
                } catch (e) {
                  toast.err(feedbackError(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              确认入账
            </button>
          </Sheet>,
          document.body,
        )}

      {rhythmOpen &&
        createPortal(
          <Sheet onClose={() => setRhythmOpen(false)} title="修改节奏">
            <p className="mt-3 text-[11px] font-bold text-muted">每周天数</p>
            <div className="mt-2 grid grid-cols-7 gap-1.5">
              {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDaysDraft(d)}
                  className={`rounded-md py-2.5 text-sm font-extrabold ${
                    daysDraft === d ? "bg-accent text-accent-ink" : "border border-line bg-elevated"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
            <p className="mt-4 text-[11px] font-bold text-muted">单次时长</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SESSION_MINUTE_OPTIONS.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMinutesDraft(m)}
                  className={`rounded-md px-3 py-2 text-xs font-bold ${
                    minutesDraft === m ? "bg-accent text-accent-ink" : "border border-line bg-elevated"
                  }`}
                >
                  {m} 分
                </button>
              ))}
            </div>
            <button
              type="button"
              disabled={busy}
              className="pressable mt-4 w-full rounded-md bg-accent py-3 text-sm font-extrabold text-accent-ink disabled:opacity-50"
              onClick={() => {
                void patch(
                  { days_per_week: daysDraft, session_minutes: minutesDraft },
                  "节奏已更新",
                ).then(() => setRhythmOpen(false));
              }}
            >
              保存
            </button>
          </Sheet>,
          document.body,
        )}
    </div>
  );
}

function Sheet({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <button type="button" className="absolute inset-0 bg-scrim" aria-label="关闭" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-t-2xl border border-line bg-elevated px-4 pb-[max(16px,env(safe-area-inset-bottom))] pt-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold">{title}</h2>
          <button type="button" className="text-sm font-bold text-muted" onClick={onClose}>
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
