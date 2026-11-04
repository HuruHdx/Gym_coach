import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Building2,
  Dumbbell,
  Flame,
  Home,
  Loader,
  Minus,
  PersonStanding,
  Plus,
  Target,
  TrendingUp,
  Zap,
} from "lucide-react";
import { api } from "../lib/api";
import {
  DAY_OPTIONS,
  DEFAULT_PROFILE_CREATE,
  EXPERIENCES,
  GOALS,
  INJURY_PRESETS,
  SCENES,
  SESSION_MINUTE_OPTIONS,
  exercisesForMinutes,
  preferencesForScene,
  type SceneId,
} from "../lib/profileOptions";
import { writeProfileExtras } from "../lib/profileView";
import type { Experience, Goal } from "../types";

type Props = { onDone: () => void };

const TOTAL = 6;

/** 选完停一下再走，让人看清自己的选择落到了哪里。 */
const ADVANCE_MS = 220;

const THINKING_STEPS = ["读取你的画像", "从动作库里挑", "按目标排组次"];

export function Onboarding({ onDone }: Props) {
  const [step, setStep] = useState(0);
  const [dir, setDir] = useState<"next" | "prev">("next");

  const [goal, setGoal] = useState<Goal>("增肌");
  const [experience, setExperience] = useState<Experience>("进阶");
  const [days, setDays] = useState(4);
  const [minutes, setMinutes] = useState<number>(40);
  const [customMinutes, setCustomMinutes] = useState(false);
  const [customText, setCustomText] = useState("40");
  const [scene, setScene] = useState<SceneId>("gym");
  const [parts, setParts] = useState<string[]>([]);
  const [injuryNote, setInjuryNote] = useState("");
  const [weight, setWeight] = useState(70);
  const [height, setHeight] = useState(175);
  const [gender, setGender] = useState<string | null>(null);
  const [birthYear, setBirthYear] = useState<number | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const go = useCallback(
    (to: number) => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = null;
      setDir(to > step ? "next" : "prev");
      setStep(Math.max(0, Math.min(TOTAL - 1, to)));
    },
    [step],
  );

  /** 单选：记下选择，短暂停顿后自己往前走。 */
  const pickAndAdvance = useCallback((apply: () => void) => {
    apply();
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setDir("next");
      setStep((s) => Math.min(TOTAL - 1, s + 1));
      timer.current = null;
    }, ADVANCE_MS);
  }, []);

  const sceneTitle = useMemo(
    () => SCENES.find((item) => item.id === scene)?.title ?? "健身房",
    [scene],
  );

  function togglePart(tag: string) {
    setParts((prev) => (prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag]));
  }

  async function submit(payload: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      await api("/api/profile", { method: "POST", body: JSON.stringify(payload) });
      writeProfileExtras({ gender, birthYear });
      onDone();
    } catch (e) {
      // 409 = 画像已存在（刷新重进），直接放行
      if (String(e).includes("409")) {
        writeProfileExtras({ gender, birthYear });
        onDone();
      } else {
        setError(String(e));
        setBusy(false);
      }
    }
  }

  function finish() {
    if (busy) return;
    if (!Number.isFinite(weight) || weight <= 30 || weight >= 300) {
      setError("体重填 30 到 300 之间的公斤数");
      return;
    }
    if (!Number.isFinite(height) || height <= 100 || height >= 250) {
      setError("身高填 100 到 250 之间的厘米");
      return;
    }
    void submit({
      goal,
      experience,
      weight_kg: Math.round(weight * 10) / 10,
      height_cm: Math.round(height),
      days_per_week: days,
      session_minutes: minutes,
      preferences: preferencesForScene(scene),
      injuries: injuryNote.trim() ? [...parts, injuryNote.trim()] : parts,
    });
  }

  function skip() {
    if (busy) return;
    void submit({ ...DEFAULT_PROFILE_CREATE });
  }

  const anim = dir === "next" ? "ob-next" : "ob-prev";

  return (
    <div className="noise mx-auto flex h-dvh max-w-md flex-col bg-bg">
      <div className="relative z-10 flex min-h-0 flex-1 flex-col">
        {/* ---- 顶部：进度 + 跳过 ---- */}
        <header className="shrink-0 px-page pt-5">
          <div className="flex items-center justify-between gap-3">
            <span className="num text-[10px] font-semibold tracking-[0.1em] text-soft">
              {String(step + 1).padStart(2, "0")} / {String(TOTAL).padStart(2, "0")}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={skip}
              className="pressable -mr-1 px-1 py-1 text-[11px] font-semibold text-muted disabled:opacity-40"
            >
              跳过
            </button>
          </div>
          <div className="mt-2 flex gap-1" aria-hidden>
            {Array.from({ length: TOTAL }, (_, i) => (
              <span key={i} className="h-0.5 flex-1 overflow-hidden rounded-full bg-line">
                <i className={`ob-seg block h-full bg-accent ${i <= step ? "is-on" : ""}`} />
              </span>
            ))}
          </div>
        </header>

        {/* ---- 主内容：切屏时整屏滑入 ---- */}
        <div key={step} className={`flex min-h-0 flex-1 flex-col ${anim}`}>
          {step === 0 && (
            <Question title="你的目标是？" sub="决定组次区间和强度，之后可以改">
              {GOALS.map((item, i) => (
                <OptionRow
                  key={item.value}
                  index={i}
                  icon={<GoalIcon goal={item.value} />}
                  title={item.value}
                  sub={item.sub}
                  selected={goal === item.value}
                  onClick={() => pickAndAdvance(() => setGoal(item.value))}
                />
              ))}
            </Question>
          )}

          {step === 1 && (
            <Question title="练了多久了？" sub="决定每周容量和加重步进">
              {EXPERIENCES.map((item, i) => (
                <OptionRow
                  key={item.value}
                  index={i}
                  icon={<LevelIcon level={item.value} />}
                  title={item.value}
                  sub={item.sub}
                  selected={experience === item.value}
                  onClick={() => pickAndAdvance(() => setExperience(item.value))}
                />
              ))}
            </Question>
          )}

          {step === 2 && (
            <Question title="你的训练节奏" sub="只用来算单次容量，不会催你打卡" compact>
              <p className="text-[11px] font-semibold tracking-wide text-soft">每周几天</p>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {DAY_OPTIONS.map((item) => (
                  <NumberTile
                    key={item}
                    value={item}
                    unit="天"
                    selected={days === item}
                    onClick={() => setDays(item)}
                  />
                ))}
              </div>

              <p className="mt-5 text-[11px] font-semibold tracking-wide text-soft">单次多久</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {SESSION_MINUTE_OPTIONS.map((item) => (
                  <Pill
                    key={item}
                    selected={!customMinutes && minutes === item}
                    onClick={() => {
                      setCustomMinutes(false);
                      setMinutes(item);
                    }}
                  >
                    {item} 分
                  </Pill>
                ))}
                <Pill
                  selected={customMinutes}
                  onClick={() => {
                    setCustomMinutes(true);
                    if ((SESSION_MINUTE_OPTIONS as readonly number[]).includes(minutes)) {
                      setCustomText(String(minutes));
                    }
                  }}
                >
                  {customMinutes && !(SESSION_MINUTE_OPTIONS as readonly number[]).includes(minutes)
                    ? `${minutes} 分`
                    : "自定义"}
                </Pill>
              </div>

              {customMinutes && (
                <div className="ob-stagger mt-2.5 flex items-center gap-2">
                  <input
                    type="number"
                    inputMode="numeric"
                    min={15}
                    max={180}
                    value={customText}
                    placeholder="输入分钟"
                    onChange={(event) => {
                      setCustomText(event.target.value);
                      const n = Number(event.target.value);
                      if (Number.isFinite(n) && n >= 15 && n <= 180) setMinutes(Math.round(n));
                    }}
                    onBlur={() => {
                      const n = Number(customText);
                      if (!Number.isFinite(n) || n < 15 || n > 180) {
                        setCustomText("40");
                        setMinutes(40);
                      } else {
                        setMinutes(Math.round(n));
                        setCustomText(String(Math.round(n)));
                      }
                    }}
                    className="num w-[92px] rounded-sm border border-line-strong bg-elevated px-3 py-2 text-center text-base font-semibold outline-none"
                  />
                  <span className="text-[12px] text-muted">分钟</span>
                  <span className="text-[11px] text-soft">15~180</span>
                </div>
              )}

              <p className="mt-2.5 text-[11px] leading-relaxed text-muted">
                {exercisesForMinutes(minutes)} · {sceneTitle}
              </p>
            </Question>
          )}

          {step === 3 && (
            <Question title="平时在哪儿练？" sub="决定能给你排哪些动作" tall>
              {SCENES.map((item, i) => (
                <SceneCard
                  key={item.id}
                  index={i}
                  scene={item.id}
                  title={item.title}
                  sub={item.sub}
                  selected={scene === item.id}
                  onClick={() => pickAndAdvance(() => setScene(item.id))}
                />
              ))}
            </Question>
          )}

          {step === 4 && (
            <Question title="有要避开的部位吗？" sub="可多选。没有就往下走" compact>
              <div className="flex flex-wrap gap-2">
                {INJURY_PRESETS.map((tag) => (
                  <Pill key={tag} selected={parts.includes(tag)} onClick={() => togglePart(tag)}>
                    {tag}
                  </Pill>
                ))}
              </div>
              <input
                value={injuryNote}
                onChange={(event) => setInjuryNote(event.target.value)}
                placeholder="补充一句，例如「左膝术后半年」（可选）"
                className="mt-3 w-full rounded-sm border border-line bg-bg px-3 py-2.5 text-base outline-none"
              />
              <div className="mt-3 flex items-start gap-2 rounded-sm bg-done-bg px-3 py-2.5">
                <AlertCircle size={13} className="mt-0.5 shrink-0 text-ok" />
                <p className="text-[11px] font-medium leading-relaxed text-ok">
                  命中部位的动作会直接不给你，只在卡上写原因，不会偷偷换成别的。
                </p>
              </div>
            </Question>
          )}

          {step === 5 && (
            <Question title="最后，身体数据" sub="体重现在就要用，其余留给以后算热量" compact>
              <div className="rounded-md border border-line bg-elevated px-3.5">
                <StepperRow
                  label="体重"
                  hint="相对强度基准"
                  unit="kg"
                  step={0.5}
                  min={31}
                  max={299}
                  value={weight}
                  decimals={1}
                  onChange={setWeight}
                />
                <StepperRow
                  label="身高"
                  hint="可选"
                  unit="cm"
                  step={1}
                  min={120}
                  max={230}
                  value={height}
                  decimals={0}
                  onChange={setHeight}
                />
                <div className="flex items-center justify-between gap-3 border-b border-line py-3">
                  <span className="text-[12.5px] text-muted">
                    性别
                    <i className="mt-0.5 block text-[10px] not-italic text-soft">以后算热量用</i>
                  </span>
                  <div className="flex gap-1">
                    {(["男", "女"] as const).map((item) => (
                      <Segment key={item} selected={gender === item} onClick={() => setGender(item)}>
                        {item}
                      </Segment>
                    ))}
                    <Segment selected={gender === null} onClick={() => setGender(null)}>
                      不填
                    </Segment>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 py-3">
                  <span className="text-[12.5px] text-muted">
                    出生年
                    <i className="mt-0.5 block text-[10px] not-italic text-soft">比年龄省事</i>
                  </span>
                  <YearStepper value={birthYear} onChange={setBirthYear} />
                </div>
              </div>
            </Question>
          )}
        </div>

        {error && (
          <p className="mx-page mt-2 shrink-0 rounded-sm border border-line px-3 py-2 text-[12px] text-danger">
            {error}
          </p>
        )}

        {/* ---- 底部：一屏一个主按钮 ---- */}
        <footer className="shrink-0 border-t border-line bg-bg px-page pb-[max(12px,env(safe-area-inset-bottom))] pt-3">
          {step === 5 ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={finish}
                className="pressable flex w-full items-center justify-center gap-2 rounded-md bg-accent py-3.5 font-display text-[15px] font-semibold text-accent-ink disabled:opacity-60"
              >
                {busy ? (
                  <>
                    <Loader size={15} className="animate-spin" />
                    <ThinkingText />
                  </>
                ) : (
                  "完成，开始第一次训练"
                )}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={skip}
                className="pressable mt-1 w-full py-2.5 text-[12px] font-semibold text-muted disabled:opacity-40"
              >
                先这样，以后再说
              </button>
            </>
          ) : (
            <div className="flex gap-2">
              {step > 0 && (
                <button
                  type="button"
                  onClick={() => go(step - 1)}
                  className="pressable w-[78px] shrink-0 rounded-md border border-line-strong text-[12.5px] font-semibold text-muted"
                >
                  上一步
                </button>
              )}
              <button
                type="button"
                onClick={() => go(step + 1)}
                className="pressable flex-1 rounded-md bg-accent py-3.5 font-display text-[15px] font-semibold text-accent-ink"
              >
                下一步
              </button>
            </div>
          )}
        </footer>
      </div>
    </div>
  );
}

/** 提交时的三步文案，只换字，不做位移动画。 */
function ThinkingText() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setI((n) => (n + 1) % THINKING_STEPS.length), 900);
    return () => window.clearInterval(id);
  }, []);
  return (
    <span key={i} className="ob-breathe">
      {THINKING_STEPS[i]}
    </span>
  );
}

/* ============================ 零件 ============================ */

function Question({
  title,
  sub,
  children,
  tall,
  compact,
}: {
  title: string;
  sub: string;
  children: React.ReactNode;
  tall?: boolean;
  compact?: boolean;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col px-page">
      <div className="shrink-0 pt-4">
        <h1 className="font-display text-[26px] font-semibold leading-[1.22] tracking-tight">
          {title}
        </h1>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{sub}</p>
      </div>
      <div
        className={`min-h-0 flex-1 overflow-y-auto overscroll-contain pb-4 ${
          tall ? "mt-4 flex flex-col gap-2" : compact ? "mt-5" : "mt-4 flex flex-col gap-2"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function OptionRow({
  index,
  icon,
  title,
  sub,
  selected,
  onClick,
}: {
  index: number;
  icon: React.ReactNode;
  title: string;
  sub: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      style={{ ["--i" as string]: index }}
      className={`ob-stagger pressable relative flex shrink-0 items-center gap-3 overflow-hidden rounded-md border px-3 py-3 text-left transition-[border-color,background-color] duration-state ${
        selected ? "border-ink bg-tint" : "border-line bg-elevated"
      }`}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-[3px] bg-accent" aria-hidden />}
      <span
        className={`grid h-[34px] w-[34px] shrink-0 place-items-center rounded-sm transition-colors duration-state ${
          selected ? "bg-accent text-accent-ink" : "bg-tint text-accent-text"
        }`}
      >
        {selected ? <Tick /> : icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] font-semibold tracking-tight">{title}</span>
        <span className="mt-0.5 block text-[11px] leading-snug text-muted">{sub}</span>
      </span>
    </button>
  );
}

function SceneCard({
  index,
  scene,
  title,
  sub,
  selected,
  onClick,
}: {
  index: number;
  scene: SceneId;
  title: string;
  sub: string;
  selected: boolean;
  onClick: () => void;
}) {
  const Glyph = scene === "gym" ? Dumbbell : scene === "home" ? Home : PersonStanding;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      style={{ ["--i" as string]: index }}
      className={`ob-stagger pressable relative flex flex-1 items-center gap-3 overflow-hidden rounded-md border px-3.5 text-left transition-[border-color,background-color] duration-state ${
        selected ? "border-accent bg-tint" : "border-line bg-elevated"
      }`}
    >
      <Glyph
        size={104}
        strokeWidth={1.2}
        aria-hidden
        className="ob-drift pointer-events-none absolute -bottom-5 -right-3 opacity-[0.06]"
      />
      <span
        className={`grid h-10 w-10 shrink-0 place-items-center rounded-full border transition-colors duration-state ${
          selected ? "border-accent bg-accent text-accent-ink" : "border-line-strong text-muted"
        }`}
      >
        {selected ? <Tick size={16} /> : <Glyph size={17} strokeWidth={1.7} />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-semibold tracking-tight">{title}</span>
        <span className="mt-0.5 block text-[11px] leading-snug text-muted">{sub}</span>
      </span>
    </button>
  );
}

function NumberTile({
  value,
  unit,
  selected,
  onClick,
}: {
  value: number;
  unit: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`pressable flex h-[80px] flex-col items-center justify-center gap-0.5 rounded-md border transition-[background-color,border-color,color] duration-state ${
        selected ? "ob-bump border-ink bg-ink text-[var(--bg)]" : "border-line bg-elevated"
      }`}
    >
      <b className="num text-[27px] font-semibold leading-none tracking-tight">{value}</b>
      <span className={`text-[10px] font-medium ${selected ? "opacity-60" : "text-muted"}`}>
        {unit}
      </span>
    </button>
  );
}

function Pill({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`pressable rounded-full border px-3.5 py-2 text-[12.5px] font-semibold transition-[background-color,border-color,color] duration-state ${
        selected ? "border-accent bg-accent text-accent-ink" : "border-line-strong bg-elevated text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function Segment({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`rounded-sm border px-2.5 py-1.5 text-[12px] font-semibold transition-[background-color,border-color,color] duration-state ${
        selected ? "border-accent bg-accent text-accent-ink" : "border-line-strong text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function StepperRow({
  label,
  hint,
  unit,
  step,
  min,
  max,
  value,
  decimals,
  onChange,
}: {
  label: string;
  hint: string;
  unit: string;
  step: number;
  min: number;
  max: number;
  value: number;
  decimals: number;
  onChange: (next: number) => void;
}) {
  const clamp = (next: number) => Math.min(max, Math.max(min, Math.round(next * 10) / 10));
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line py-3">
      <span className="text-[12.5px] text-muted">
        {label}
        <i className="mt-0.5 block text-[10px] not-italic text-soft">{hint}</i>
      </span>
      <span className="flex items-center gap-1">
        <StepBtn onClick={() => onChange(clamp(value - step))} label={`减少${label}`}>
          <Minus size={13} />
        </StepBtn>
        <span className="num min-w-[62px] text-center text-[15px] font-semibold">
          {value.toFixed(decimals)}
          <small className="ml-0.5 text-[10px] font-medium text-soft">{unit}</small>
        </span>
        <StepBtn onClick={() => onChange(clamp(value + step))} label={`增加${label}`}>
          <Plus size={13} />
        </StepBtn>
      </span>
    </div>
  );
}

function YearStepper({ value, onChange }: { value: number | null; onChange: (next: number) => void }) {
  const current = value ?? 1995;
  return (
    <span className="flex items-center gap-1">
      <StepBtn onClick={() => onChange(current - 1)} label="往前一年">
        <Minus size={13} />
      </StepBtn>
      <span className="num min-w-[52px] text-center text-[15px] font-semibold">
        {value ?? "未填"}
      </span>
      <StepBtn onClick={() => onChange(current + 1)} label="往后一年">
        <Plus size={13} />
      </StepBtn>
    </span>
  );
}

function StepBtn({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="pressable grid h-[29px] w-[29px] place-items-center rounded-sm border border-line-strong bg-elevated"
    >
      {children}
    </button>
  );
}

/** 描出来的勾，不是淡入 */
function Tick({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M5 12.5 10 17.5 19 7"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="ob-tick"
      />
    </svg>
  );
}

function GoalIcon({ goal }: { goal: Goal }) {
  const Icon = goal === "增肌" ? Dumbbell : goal === "减脂" ? Flame : goal === "力量" ? Zap : Target;
  return <Icon size={17} strokeWidth={1.7} />;
}

function LevelIcon({ level }: { level: Experience }) {
  const Icon = level === "新手" ? Target : level === "进阶" ? TrendingUp : Building2;
  return <Icon size={17} strokeWidth={1.7} />;
}
