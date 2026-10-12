import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

type Props = { profile: Profile; onUpdated: () => void; onResetOnboarding: () => void };

function currentEquipment(profile: Profile): string[] {
  const prefs = profile.preferences || [];
  return prefs.length ? prefs : [...DEFAULT_EQUIPMENT];
}

/** 二级资料页：低频档案，点选即存，无全局「保存」大按钮 */
export function ProfileSettingsPage({ profile, onUpdated, onResetOnboarding }: Props) {
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [height, setHeight] = useState<number | "">(profile.height_cm ?? "");
  const equipment = currentEquipment(profile);

  useEffect(() => {
    setHeight(profile.height_cm ?? "");
  }, [profile.height_cm]);

  async function patch(body: Record<string, unknown>, label?: string) {
    setBusy(true);
    try {
      await api("/api/profile", { method: "PATCH", body: JSON.stringify(body) });
      onUpdated();
      if (label) {
        setToast(label);
        window.setTimeout(() => setToast(null), 1400);
      }
    } catch (e) {
      alert(String(e));
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
      <div className="flex items-center justify-between gap-3">
        <Link
          to="/me"
          className="pressable rounded-md border border-line bg-elevated px-3 py-2 text-xs font-bold"
        >
          ← 返回
        </Link>
        {toast && <span className="text-xs font-bold text-[color:var(--ok)] rise-in">{toast}</span>}
      </div>

      <p className="font-display mt-4 text-[11px] font-extrabold uppercase tracking-[0.12em] text-muted">
        设置
      </p>
      <h1 className="font-display text-[26px] font-bold tracking-tight">训练资料</h1>
      <p className="mt-1 text-sm text-muted">低频档案，改完即生效。体重和伤痛在「我的」里改。</p>

      <section className="mt-6">
        <RowLabel>目标</RowLabel>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {GOALS.map((g) => (
            <Chip
              key={g.value}
              active={profile.goal === g.value}
              label={g.value}
              disabled={busy}
              onClick={() => patch({ goal: g.value }, "目标已更新")}
            />
          ))}
        </div>
      </section>

      <section className="mt-5">
        <RowLabel>身份</RowLabel>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {EXPERIENCES.map((e) => (
            <Chip
              key={e.value}
              active={profile.experience === e.value}
              label={e.value}
              disabled={busy}
              onClick={() => patch({ experience: e.value }, "身份已更新")}
            />
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">
          新手：系统练不满 1 年 · 进阶：动作稳定知道重量 · 老炮：多年规律训
        </p>
      </section>

      <section className="mt-5">
        <RowLabel>身高 cm</RowLabel>
        <div className="mt-2 flex gap-2">
          <input
            type="number"
            className="flex-1 rounded-md border border-line bg-elevated px-3 py-2.5 font-display font-bold outline-none"
            value={height}
            placeholder="可选"
            onChange={(e) =>
              setHeight(e.target.value === "" ? "" : Number(e.target.value))
            }
          />
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-line px-4 text-sm font-bold disabled:opacity-50"
            onClick={() => {
              const height_cm =
                height === "" || Number(height) <= 0 ? null : Number(height);
              void patch({ height_cm }, "身高已更新");
            }}
          >
            更新
          </button>
        </div>
      </section>

      <section className="mt-5">
        <RowLabel>每周训练天数</RowLabel>
        <div className="mt-2 grid grid-cols-7 gap-1.5">
          {[1, 2, 3, 4, 5, 6, 7].map((d) => (
            <button
              key={d}
              type="button"
              disabled={busy}
              onClick={() => patch({ days_per_week: d }, "每周天数已更新")}
              className={`rounded-md py-2.5 font-display text-sm font-extrabold disabled:opacity-50 ${
                profile.days_per_week === d
                  ? "bg-accent text-accent-ink"
                  : "border border-line bg-elevated"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-5">
        <RowLabel>默认单次时长</RowLabel>
        <p className="mt-1 text-xs text-muted">全局默认；某天赶时间可在教练对话里临时说。</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SESSION_MINUTE_OPTIONS.map((m) => (
            <Chip
              key={m}
              active={(profile.session_minutes ?? 45) === m}
              label={`${m} 分`}
              disabled={busy}
              onClick={() => patch({ session_minutes: m }, "默认时长已更新")}
            />
          ))}
        </div>
      </section>

      <section className="mt-5">
        <RowLabel>默认器械底座</RowLabel>
        <p className="mt-1 text-xs text-muted">常去的场地；出差酒店请当次对话说明，不必改这里。</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {EQUIPMENT_OPTIONS.map((e) => (
            <Chip
              key={e.value}
              active={equipment.includes(e.value)}
              label={e.value}
              disabled={busy}
              onClick={() => toggleEquipment(e.value)}
            />
          ))}
        </div>
      </section>

      <section className="mt-10 border-t border-line pt-5">
        <button
          type="button"
          className="pressable w-full rounded-md border border-line py-3 text-sm font-bold text-muted"
          onClick={async () => {
            if (!confirm("清除画像并重新走引导？")) return;
            try {
              await api("/api/profile", { method: "DELETE" });
              onResetOnboarding();
            } catch (e) {
              alert(String(e));
            }
          }}
        >
          重新建画像
        </button>
      </section>
    </div>
  );
}

function RowLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-bold uppercase tracking-widest text-muted">{children}</h2>
  );
}

function Chip({
  active,
  label,
  onClick,
  disabled,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md px-3 py-2 text-xs font-bold disabled:opacity-50 ${
        active ? "bg-accent text-accent-ink" : "border border-line bg-elevated"
      }`}
    >
      {label}
    </button>
  );
}
