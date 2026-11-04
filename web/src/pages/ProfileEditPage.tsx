import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { DateWheelPickerSheet } from "../components/WheelPickerSheet";
import { api } from "../lib/api";
import {
  AVOID_PARTS,
  DAY_OPTIONS,
  EXPERIENCE_OPTIONS,
  GOAL_OPTIONS,
  MINUTE_PRESETS,
  SCENES,
  displayNameOf,
  formatBirthDateLabel,
  injuriesToSave,
  injuryNote,
  partSelected,
  readProfileExtras,
  sceneFromPreferences,
  writeProfileExtras,
  type AuthUser,
  type SceneId,
} from "../lib/profileView";
import type { Experience, Goal, Profile } from "../types";

type Props = {
  profile: Profile;
  onUpdated: () => Promise<unknown> | void;
};

function preferencesFor(id: SceneId): string[] {
  const scene = SCENES.find((item) => item.id === id) ?? SCENES[0];
  return [...scene.preferences];
}

export function ProfileEditPage({ profile, onUpdated }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const extras = readProfileExtras();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<AuthUser>("/api/auth/me"),
  });
  const [goal, setGoal] = useState<Goal>(profile.goal);
  const [experience, setExperience] = useState<Experience>(profile.experience);
  const [days, setDays] = useState(profile.days_per_week);
  const [minuteText, setMinuteText] = useState(String(profile.session_minutes ?? 45));
  const [scene, setScene] = useState<SceneId>(sceneFromPreferences(profile.preferences));
  const [parts, setParts] = useState<string[]>(() =>
    AVOID_PARTS.filter((part) => partSelected(profile.injuries || [], part.stored, part.label)).map(
      (part) => part.stored,
    ),
  );
  const [note, setNote] = useState(() => injuryNote(profile.injuries || []));
  const [weightText, setWeightText] = useState(
    profile.weight_kg != null ? String(profile.weight_kg) : "",
  );
  const [heightText, setHeightText] = useState(
    profile.height_cm != null ? String(profile.height_cm) : "",
  );
  const [gender, setGender] = useState<string | null>(extras.gender);
  const [birthDate, setBirthDate] = useState<string | null>(extras.birthDate);
  const [nick, setNick] = useState("");
  const [picker, setPicker] = useState<"gender" | "birth" | null>(null);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const shownName = nick.trim() || displayNameOf(me);
  const letter = shownName.slice(0, 1);
  const minutes = Number(minuteText);

  useEffect(() => {
    if (me?.display_name != null) setNick(me.display_name);
  }, [me?.id, me?.display_name]);

  function flash(message: string) {
    setHint(message);
    window.setTimeout(() => setHint(null), 1600);
  }

  function togglePart(stored: string) {
    setParts((prev) => (prev.includes(stored) ? prev.filter((item) => item !== stored) : [...prev, stored]));
  }

  async function save() {
    if (busy) return;
    let weight_kg: number | null = null;
    if (weightText.trim() !== "") {
      const weight = Number(weightText);
      if (!Number.isFinite(weight) || weight <= 30 || weight >= 300) {
        alert("体重填 30 到 300 之间的公斤数，或留空");
        return;
      }
      weight_kg = Math.round(weight * 10) / 10;
    }
    if (!Number.isFinite(minutes) || minutes < 15 || minutes > 180) {
      alert("单次时长填 15 到 180 分钟");
      return;
    }
    let height_cm: number | null = null;
    if (heightText.trim() !== "") {
      const height = Number(heightText);
      if (!Number.isFinite(height) || height <= 100 || height >= 250) {
        alert("身高填 100 到 250 之间的厘米，或留空");
        return;
      }
      height_cm = Math.round(height);
    }
    setBusy(true);
    try {
      await api("/api/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ display_name: nick.trim().slice(0, 40) || null }),
      });
      await api("/api/profile", {
        method: "PATCH",
        body: JSON.stringify({
          goal,
          experience,
          days_per_week: days,
          session_minutes: Math.round(minutes),
          preferences: preferencesFor(scene),
          injuries: injuriesToSave(parts, note),
          weight_kg,
          height_cm,
        }),
      });
      writeProfileExtras({ gender, birthDate });
      await qc.invalidateQueries({ queryKey: ["me"] });
      await qc.invalidateQueries({ queryKey: ["weight-history"] });
      await onUpdated();
      navigate("/me");
    } catch (error) {
      alert(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col px-page pb-8 pt-2">
      <header className="sticky top-0 z-10 -mx-page bg-bg px-page py-3">
        <h1 className="font-display text-title font-semibold tracking-tight">编辑资料</h1>
      </header>

      <div className="mt-2 flex flex-col items-center gap-2 pb-4">
        <div className="grid h-[84px] w-[84px] place-items-center rounded-xl bg-ink font-display text-display font-semibold text-accent-ink">
          {letter}
        </div>
        <button
          type="button"
          onClick={() => flash("头像暂未接入")}
          className="pressable rounded-full border border-line bg-elevated px-3.5 py-1.5 text-xs font-semibold"
        >
          更换头像
        </button>
      </div>

      <GroupTitle>称呼</GroupTitle>
      <Card>
        <FieldLabel>昵称</FieldLabel>
        <input
          type="text"
          maxLength={40}
          value={nick}
          placeholder="例如：阿虎"
          onChange={(e) => setNick(e.target.value)}
          className="mt-2 w-full rounded-sm border border-line bg-bg px-3 py-2.5 text-[15px] font-semibold outline-none"
          style={{ fontSize: 16 }}
        />
        <p className="mt-1.5 text-[11px] text-muted">不填则用系统给你取的默认称呼</p>
      </Card>

      <GroupTitle>训练目标</GroupTitle>
      <Card>
        <FieldLabel>目标</FieldLabel>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {GOAL_OPTIONS.map((item) => (
            <Pill key={item} active={goal === item} onClick={() => setGoal(item)}>
              {item}
            </Pill>
          ))}
        </div>
      </Card>

      <Card>
        <FieldLabel>经验</FieldLabel>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {EXPERIENCE_OPTIONS.map((item) => (
            <Pill key={item.value} active={experience === item.value} onClick={() => setExperience(item.value)}>
              {item.label}
            </Pill>
          ))}
        </div>
      </Card>

      <Card>
        <FieldLabel>每周练几天</FieldLabel>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {DAY_OPTIONS.map((item) => (
            <Pill key={item} active={days === item} onClick={() => setDays(item)}>
              {item}
            </Pill>
          ))}
        </div>
      </Card>

      <Card>
        <FieldLabel>单次时长</FieldLabel>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {MINUTE_PRESETS.map((item) => (
            <Pill key={item} active={minutes === item} onClick={() => setMinuteText(String(item))}>
              {item}
            </Pill>
          ))}
        </div>
        <div className="mt-2.5 flex items-center gap-2">
          <span className="text-xs text-muted">自定义</span>
          <input
            type="number"
            inputMode="numeric"
            min={15}
            max={180}
            value={minuteText}
            placeholder="输入分钟"
            onChange={(event) => setMinuteText(event.target.value)}
            className="min-w-0 flex-1 rounded-sm border border-line bg-bg px-3 py-2 text-sm font-semibold outline-none"
          />
          <span className="text-xs text-muted">分钟</span>
        </div>
      </Card>

      <Card>
        <FieldLabel>训练场景</FieldLabel>
        <div className="mt-2 flex flex-col gap-2">
          {SCENES.map((item) => {
            const on = scene === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setScene(item.id)}
                className={`rounded-md border px-3.5 py-3 text-left ${
                  on ? "border-accent bg-accent text-accent-ink" : "border-line bg-bg"
                }`}
              >
                <b className="block text-sm font-bold">{item.title}</b>
                <span className={`mt-0.5 block text-xs ${on ? "opacity-70" : "text-muted"}`}>
                  {item.sub}
                </span>
              </button>
            );
          })}
        </div>
      </Card>

      <Card>
        <FieldLabel>要避开的部位</FieldLabel>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {AVOID_PARTS.map((part) => (
            <Pill key={part.stored} active={parts.includes(part.stored)} onClick={() => togglePart(part.stored)}>
              {part.label}
            </Pill>
          ))}
        </div>
        <input
          value={note}
          placeholder="说明一下（可选）"
          onChange={(event) => setNote(event.target.value)}
          className="mt-2.5 w-full rounded-sm border border-line bg-bg px-3 py-2.5 text-[13px] outline-none"
        />
      </Card>

      <GroupTitle>身体数据</GroupTitle>
      <Card>
        <BodyRow label="体重">
          <input
            type="number"
            inputMode="decimal"
            value={weightText}
            placeholder="未填"
            onChange={(event) => setWeightText(event.target.value)}
            className="w-20 rounded-sm border border-line bg-bg px-2.5 py-2 text-right text-sm font-semibold outline-none"
          />
          <span className="text-xs text-muted">kg</span>
        </BodyRow>
        <BodyRow label="身高">
          <input
            type="number"
            inputMode="numeric"
            value={heightText}
            placeholder="未填"
            onChange={(event) => setHeightText(event.target.value)}
            className="w-20 rounded-sm border border-line bg-bg px-2.5 py-2 text-right text-sm font-semibold outline-none"
          />
          <span className="text-xs text-muted">cm</span>
        </BodyRow>
        <BodyRow label="性别" onClick={() => setPicker("gender")}>
          <span className="text-sm font-semibold">{gender ?? "未填"}</span>
          <span className="text-sm text-muted">›</span>
        </BodyRow>
        <BodyRow label="出生日期" last onClick={() => setPicker("birth")}>
          <span className="text-sm font-semibold">{formatBirthDateLabel(birthDate)}</span>
          <span className="text-sm text-muted">›</span>
        </BodyRow>
      </Card>

      <button
        type="button"
        disabled={busy}
        onClick={() => void save()}
        className="pressable mt-5 w-full rounded-md bg-accent py-4 font-display text-base font-extrabold text-accent-ink disabled:opacity-60"
      >
        {busy ? "保存中…" : "保存"}
      </button>
      <p className="py-3 text-center text-[10px] text-muted/80">这些信息只用于生成安全的训练计划</p>

      {hint && (
        <p className="pointer-events-none fixed bottom-24 left-1/2 z-30 -translate-x-1/2 rounded-full bg-ink px-3 py-1.5 text-xs font-bold text-[var(--bg)]">
          {hint}
        </p>
      )}

      {picker === "gender" && (
        <PickerSheet title="性别" onClose={() => setPicker(null)}>
          <div className="flex gap-2">
            {(["男", "女"] as const).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => {
                  setGender(item);
                  setPicker(null);
                }}
                className={`flex-1 rounded-md py-3 text-sm font-bold ${
                  gender === item ? "bg-accent text-accent-ink" : "border border-line bg-elevated"
                }`}
              >
                {item}
              </button>
            ))}
            <button
              type="button"
              onClick={() => {
                setGender(null);
                setPicker(null);
              }}
              className={`flex-1 rounded-md py-3 text-sm font-bold ${
                gender === null ? "bg-accent text-accent-ink" : "border border-line bg-elevated"
              }`}
            >
              不填
            </button>
          </div>
        </PickerSheet>
      )}
      <DateWheelPickerSheet
        open={picker === "birth"}
        value={birthDate}
        onClose={() => setPicker(null)}
        onConfirm={(next) => {
          setBirthDate(next);
          setPicker(null);
        }}
      />
    </div>
  );
}

function GroupTitle({ children }: { children: string }) {
  return (
    <h2 className="mb-2 mt-4 px-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
      {children}
    </h2>
  );
}

function Card({ children }: { children: ReactNode }) {
  return <section className="mb-2 rounded-md border border-line bg-elevated p-3.5">{children}</section>;
}

function FieldLabel({ children }: { children: string }) {
  return <p className="text-[13px] font-bold">{children}</p>;
}

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-4 py-2 text-[13px] font-semibold ${
        active ? "bg-accent text-accent-ink" : "border border-line"
      }`}
    >
      {children}
    </button>
  );
}

function BodyRow({
  label,
  last,
  onClick,
  children,
}: {
  label: string;
  last?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  const className = `flex w-full items-center justify-between gap-3 py-3 text-left ${last ? "" : "border-b border-line"}`;
  const inner = (
    <>
      <span className="text-[13px] text-muted">{label}</span>
      <span className="flex items-center gap-2">{children}</span>
    </>
  );
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={className}>
        {inner}
      </button>
    );
  }
  return <div className={className}>{inner}</div>;
}

function PickerSheet({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 sm:items-center sm:p-4">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-t-2xl border border-line bg-bg px-5 pb-8 pt-5 sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-extrabold">{title}</h2>
          <button type="button" className="text-sm font-bold text-muted" onClick={onClose}>
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
