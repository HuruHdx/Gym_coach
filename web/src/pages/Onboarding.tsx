import { useMemo, useState } from "react";
import { api } from "../lib/api";
import {
  DEFAULT_EQUIPMENT,
  DEFAULT_PROFILE_CREATE,
  EQUIPMENT_OPTIONS,
  EXPERIENCES,
  GOALS,
  INJURY_PRESETS,
  SESSION_MINUTE_OPTIONS,
  type EquipmentTag,
} from "../lib/profileOptions";
import type { Experience, Goal } from "../types";

type Props = { onDone: () => void };

export function Onboarding({ onDone }: Props) {
  const [step, setStep] = useState(0);
  const [goal, setGoal] = useState<Goal>("增肌");
  const [experience, setExperience] = useState<Experience>("进阶");
  const [height, setHeight] = useState<number | "">(175);
  const [weight, setWeight] = useState(70);
  const [days, setDays] = useState(4);
  const [sessionMinutes, setSessionMinutes] = useState(45);
  const [equipment, setEquipment] = useState<EquipmentTag[]>([...DEFAULT_EQUIPMENT]);
  const [injuryInput, setInjuryInput] = useState("");
  const [injuries, setInjuries] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const title = useMemo(
    () => ["你的目标", "你的身份", "身体与节奏", "训练条件", "伤痛备注"][step],
    [step],
  );

  async function save(payload: Record<string, unknown>) {
    setBusy(true);
    try {
      await api("/api/profile", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      onDone();
    } catch (e) {
      if (String(e).includes("409")) onDone();
      else alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  function payloadFromState() {
    const height_cm =
      height === "" || Number(height) <= 0 ? null : Number(height);
    return {
      goal,
      experience,
      weight_kg: weight,
      height_cm,
      days_per_week: days,
      session_minutes: sessionMinutes,
      preferences: equipment.length ? equipment : [...DEFAULT_EQUIPMENT],
      injuries,
    };
  }

  async function finish() {
    await save(payloadFromState());
  }

  async function skip() {
    await save({ ...DEFAULT_PROFILE_CREATE });
  }

  function toggleEquipment(tag: EquipmentTag) {
    setEquipment((prev) =>
      prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag],
    );
  }

  function toggleInjury(tag: string) {
    setInjuries((prev) =>
      prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag],
    );
  }

  const heightLabel = height === "" || !height ? "未填" : `${height} cm`;
  const equipLabel =
    equipment.length === 0 || equipment.length === DEFAULT_EQUIPMENT.length
      ? "器械不限"
      : equipment.join("、");

  return (
    <div className="noise mx-auto flex h-dvh max-w-md flex-col bg-bg">
      <div className="relative z-10 flex min-h-0 flex-1 flex-col px-5 pb-6 pt-10">
        <div
          className="pointer-events-none absolute -right-8 -top-4 h-44 w-44 rounded-full border-[16px] border-accent/30"
          aria-hidden
        />

        <div className="flex items-start justify-between gap-3 rise-in">
          <div>
            <p className="font-display text-xs font-extrabold uppercase tracking-[0.14em] text-muted">
              Gym Coach · 建画像
            </p>
            <h1 className="font-display mt-3 text-3xl font-extrabold leading-none tracking-tight">
              {title}
            </h1>
            <p className="mt-2 text-sm text-muted">海报式点选，随时可跳过；画像可随时在「我的」改。</p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={skip}
            className="pressable shrink-0 rounded-md border border-line bg-elevated px-3 py-2 text-xs font-bold text-muted"
          >
            跳过
          </button>
        </div>

        <div className="mt-6 flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-elevated shadow-[0_16px_48px_rgba(18,20,15,0.08)] rise-in rise-in-delay-1 pop-in">
          <div className="relative overflow-hidden border-b border-line bg-gradient-to-br from-[var(--hero-a)] to-bg px-5 py-5">
            <div
              className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rotate-12 bg-accent/80"
              style={{ clipPath: "polygon(30% 0, 100% 0, 100% 100%, 0 70%)" }}
              aria-hidden
            />
            <p className="relative text-[11px] font-bold uppercase tracking-[0.12em] text-muted">
              Step {step + 1} / 5
            </p>
            <p className="font-display relative mt-2 text-xl font-extrabold">
              {goal} · {experience}
            </p>
            <p className="relative mt-1 text-xs text-muted">
              {heightLabel} · {weight} kg · 每周 {days} 练 · {sessionMinutes} 分钟
            </p>
            <p className="relative mt-0.5 text-xs text-muted">
              {equipLabel}
              {injuries.length ? ` · 伤痛 ${injuries.join("、")}` : ""}
            </p>
            <div className="relative mt-4 flex gap-1.5">
              {[0, 1, 2, 3, 4].map((i) => (
                <span
                  key={i}
                  className={`h-1 flex-1 rounded-full ${i <= step ? "bg-accent" : "bg-line"}`}
                />
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {step === 0 && (
              <div className="grid gap-2">
                {GOALS.map((g) => (
                  <PosterChoice
                    key={g.value}
                    active={goal === g.value}
                    title={g.value}
                    sub={g.sub}
                    onClick={() => setGoal(g.value)}
                  />
                ))}
              </div>
            )}
            {step === 1 && (
              <div className="grid gap-2">
                {EXPERIENCES.map((e) => (
                  <PosterChoice
                    key={e.value}
                    active={experience === e.value}
                    title={e.value}
                    sub={e.sub}
                    onClick={() => setExperience(e.value)}
                  />
                ))}
              </div>
            )}
            {step === 2 && (
              <div className="space-y-4">
                <label className="block">
                  <span className="text-[11px] font-bold uppercase tracking-widest text-muted">
                    身高 cm（可选）
                  </span>
                  <input
                    type="number"
                    className="mt-2 w-full rounded-md border border-line bg-bg px-3 py-3 font-display text-2xl font-extrabold outline-none"
                    value={height}
                    placeholder="175"
                    onChange={(e) =>
                      setHeight(e.target.value === "" ? "" : Number(e.target.value))
                    }
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] font-bold uppercase tracking-widest text-muted">
                    体重 kg
                  </span>
                  <input
                    type="number"
                    className="mt-2 w-full rounded-md border border-line bg-bg px-3 py-3 font-display text-2xl font-extrabold outline-none"
                    value={weight}
                    onChange={(e) => setWeight(Number(e.target.value))}
                  />
                </label>
                <label className="block">
                  <span className="text-[11px] font-bold uppercase tracking-widest text-muted">
                    每周练几天
                  </span>
                  <div className="mt-2 grid grid-cols-7 gap-1.5">
                    {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setDays(d)}
                        className={`rounded-md py-3 font-display text-sm font-extrabold ${
                          days === d
                            ? "bg-accent text-accent-ink"
                            : "border border-line bg-bg text-ink"
                        }`}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </label>
                <label className="block">
                  <span className="text-[11px] font-bold uppercase tracking-widest text-muted">
                    单次大概多久
                  </span>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {SESSION_MINUTE_OPTIONS.map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setSessionMinutes(m)}
                        className={`rounded-md px-3 py-2.5 font-display text-sm font-extrabold ${
                          sessionMinutes === m
                            ? "bg-accent text-accent-ink"
                            : "border border-line bg-bg text-ink"
                        }`}
                      >
                        {m} 分
                      </button>
                    ))}
                  </div>
                </label>
              </div>
            )}
            {step === 3 && (
              <div className="space-y-3">
                <p className="text-sm text-muted">多选你常能用到的；全选等于不限。教练排课会优先这些。</p>
                <div className="grid gap-2">
                  {EQUIPMENT_OPTIONS.map((e) => (
                    <PosterChoice
                      key={e.value}
                      active={equipment.includes(e.value)}
                      title={e.value}
                      sub={e.sub}
                      onClick={() => toggleEquipment(e.value)}
                    />
                  ))}
                </div>
              </div>
            )}
            {step === 4 && (
              <div className="space-y-3">
                <p className="text-sm text-muted">有伤痛会剔除高风险动作；没有就留空。</p>
                <div className="flex flex-wrap gap-2">
                  {INJURY_PRESETS.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => toggleInjury(tag)}
                      className={`rounded-full px-3 py-1.5 text-xs font-bold ${
                        injuries.includes(tag)
                          ? "bg-accent text-accent-ink"
                          : "border border-line bg-bg"
                      }`}
                    >
                      {tag}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    className="flex-1 rounded-md border border-line bg-bg px-3 py-2.5 text-sm outline-none"
                    placeholder="其他，例如：左膝术后"
                    value={injuryInput}
                    onChange={(e) => setInjuryInput(e.target.value)}
                  />
                  <button
                    type="button"
                    className="rounded-md border border-line px-3 text-sm font-bold"
                    onClick={() => {
                      const v = injuryInput.trim();
                      if (v && !injuries.includes(v)) setInjuries([...injuries, v]);
                      setInjuryInput("");
                    }}
                  >
                    添加
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {injuries.length === 0 && (
                    <span className="text-sm text-muted">没有就留空，直接完成。</span>
                  )}
                  {injuries.map((i) => (
                    <button
                      key={i}
                      type="button"
                      className="rounded-full border border-line bg-bg px-3 py-1 text-xs font-bold"
                      onClick={() => setInjuries(injuries.filter((x) => x !== i))}
                    >
                      {i} ×
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          {step > 0 && (
            <button
              type="button"
              className="pressable rounded-md border border-line px-4 py-3.5 font-semibold"
              onClick={() => setStep((s) => s - 1)}
            >
              上一步
            </button>
          )}
          {step < 4 ? (
            <button
              type="button"
              className="pressable flex-1 rounded-md bg-accent py-3.5 font-display text-base font-extrabold text-accent-ink"
              onClick={() => setStep((s) => s + 1)}
            >
              下一步
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              className="pressable flex-1 rounded-md bg-accent py-3.5 font-display text-base font-extrabold text-accent-ink disabled:opacity-60"
              onClick={finish}
            >
              {busy ? "保存中…" : "完成，进入今日"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function PosterChoice({
  active,
  onClick,
  title,
  sub,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  sub: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`pressable rounded-md border px-4 py-3.5 text-left transition ${
        active
          ? "border-ink bg-accent/25 shadow-[inset_3px_0_0_var(--accent)]"
          : "border-line bg-bg"
      }`}
    >
      <div className="font-display text-base font-bold">{title}</div>
      <div className="mt-1 text-xs text-muted">{sub}</div>
    </button>
  );
}
