import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { TrainingSession } from "../types";

function coachText(summary?: string | null): string {
  if (!summary) return "";
  const marker = "教练补充：";
  const at = summary.indexOf(marker);
  if (at >= 0) return summary.slice(at + marker.length).trim();
  if (summary.startsWith("今天主要是") || summary.startsWith("这次没有勾选")) return "";
  return summary.trim();
}

function streakDays(sessions: TrainingSession[] | undefined): number {
  if (!sessions?.length) return 0;
  const doneDays = [
    ...new Set(
      sessions
        .filter((s) => s.status === "done")
        .map((s) => s.session_date)
        .filter(Boolean),
    ),
  ].sort((a, b) => (a < b ? 1 : -1));
  if (!doneDays.length) return 0;
  let streak = 1;
  for (let i = 1; i < doneDays.length; i += 1) {
    const newer = new Date(`${doneDays[i - 1]}T00:00:00`);
    const older = new Date(`${doneDays[i]}T00:00:00`);
    const gap = (newer.getTime() - older.getTime()) / 86400000;
    if (gap === 1) streak += 1;
    else break;
  }
  return streak;
}

const MUSCLE_LABEL: Record<string, string> = {
  胸: "胸部推举",
  背: "背部拉力",
  肩: "肩部稳定",
  腿: "下肢力量",
  臂: "手臂孤立",
  核心: "核心稳定",
  全身: "全身复合",
};

export function RecapPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: session, isLoading } = useQuery({
    queryKey: ["training-today"],
    queryFn: () => api<TrainingSession | null>("/api/training/today"),
  });
  const { data: history } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=30"),
  });
  const [busy, setBusy] = useState(false);
  const [local, setLocal] = useState<TrainingSession | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [editingTime, setEditingTime] = useState(false);
  const [minuteDraft, setMinuteDraft] = useState("");
  const current = local ?? session ?? null;
  const line = coachText(current?.summary);
  const doneSets = current?.sets.filter((set) => set.completed).length ?? 0;
  const exerciseCount = useMemo(() => {
    if (!current) return 0;
    return new Set(current.sets.filter((s) => s.completed).map((s) => s.exercise_name)).size;
  }, [current]);
  const themes = useMemo(() => {
    if (!current) return [] as string[];
    const seen: string[] = [];
    for (const set of current.sets) {
      const m = set.muscle || "";
      if (m && !seen.includes(m)) seen.push(m);
    }
    return seen.slice(0, 3);
  }, [current]);
  const streak = streakDays(history);
  const minutes = current?.duration_minutes;

  async function saveDuration() {
    if (!current || busy) return;
    const minutes = Number(minuteDraft);
    if (!Number.isFinite(minutes) || minutes < 1 || minutes > 300) {
      alert("填 1 到 300 分钟");
      return;
    }
    setBusy(true);
    try {
      const next = await api<TrainingSession>(`/api/training/sessions/${current.id}/duration`, {
        method: "POST",
        body: JSON.stringify({ duration_minutes: Math.round(minutes) }),
      });
      setLocal(next);
      qc.setQueryData(["training-today"], next);
      setEditingTime(false);
    } catch (error) {
      alert(String(error));
    } finally {
      setBusy(false);
    }
  }

  async function regenerate() {
    if (!current || busy) return;
    setBusy(true);
    try {
      const next = await api<TrainingSession>(`/api/training/sessions/${current.id}/resummarize`, {
        method: "POST",
      });
      setLocal(next);
      qc.setQueryData(["training-today"], next);
      setShowDetail(true);
    } catch (error) {
      alert(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="recap-poster relative flex min-h-full flex-col overflow-hidden px-5 pb-8 pt-4 text-white">
      <div className="recap-orbit pointer-events-none absolute -right-24 top-8 h-72 w-72 rounded-full" />
      <div className="recap-grid pointer-events-none absolute inset-0 opacity-40" />

      <div className="relative flex items-center justify-between">
        <button
          type="button"
          onClick={() => {
            if (window.history.length > 1) {
              navigate(-1);
            } else {
              navigate("/");
            }
          }}
          aria-label="返回"
          className="pressable flex h-8 items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 text-xs font-bold text-white/90 backdrop-blur-md transition-colors hover:bg-white/20"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
          <span>返回</span>
        </button>
        <span className="rounded border border-cyan-300/40 px-2.5 py-1 font-display text-[10px] font-extrabold tracking-[0.18em] text-cyan-200 backdrop-blur-sm">
          GYM COACH
        </span>
      </div>

      {isLoading && <p className="relative mt-16 text-sm text-white/60">正在打开结算…</p>}

      {!isLoading && !current && (
        <p className="relative mt-16 font-display text-2xl font-extrabold">今天还没有完成的训练。</p>
      )}

      {current && (
        <div className="relative mt-8 flex flex-1 flex-col">
          <div className="text-center">
            <p className="text-[11px] font-bold tracking-[0.24em] text-lime-300">SESSION CLEAR</p>
            <h1 className="mt-2 font-display text-[40px] font-extrabold italic tracking-tight text-white">
              训练完成
            </h1>
            <p className="mt-1 text-sm text-white/65">今日计划已执行</p>
            {current.session_outcome && (
              <p className="mt-2 inline-block rounded-full border border-lime-300/40 bg-lime-300/10 px-3 py-0.5 text-xs font-bold text-lime-200">
                {current.session_outcome}
              </p>
            )}
          </div>

          <div className="recap-panel mt-7 rounded-2xl border border-lime-300/35 bg-black/35 p-4 backdrop-blur-sm">
            <div className="grid grid-cols-3 gap-2 text-center">
              <Stat
                label="训练时长"
                value={minutes != null && minutes >= 1 ? String(minutes) : "—"}
                unit="分钟"
                accent
              />
              <Stat label="完成组数" value={String(doneSets)} unit="组" />
              <Stat label="坚持打卡" value={String(Math.max(streak, current.status === "done" ? 1 : 0))} unit="天" accent />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-3">
                <p className="text-[11px] text-white/55">完成动作</p>
                <p className="mt-1 font-display text-2xl font-extrabold">
                  {exerciseCount}
                  <span className="ml-1 text-sm font-bold text-white/50">个</span>
                </p>
              </div>
              <div className="rounded-xl border border-cyan-300/30 bg-gradient-to-br from-cyan-400/20 to-lime-300/10 px-3 py-3">
                <p className="text-[11px] text-cyan-100/80">本场状态</p>
                <p className="mt-1 font-display text-lg font-extrabold text-lime-200">
                  {current.session_outcome || "完成"}
                </p>
              </div>
            </div>
            {!editingTime ? (
              <button
                type="button"
                onClick={() => {
                  setMinuteDraft(minutes != null ? String(minutes) : "");
                  setEditingTime(true);
                }}
                className="mt-3 w-full text-center text-xs font-bold text-cyan-200"
              >
                {minutes != null && minutes >= 1 ? "改训练时长" : "记下训练时长"}
              </button>
            ) : (
              <div className="mt-3 flex items-center justify-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={300}
                  inputMode="numeric"
                  value={minuteDraft}
                  onChange={(e) => setMinuteDraft(e.target.value)}
                  className="w-20 rounded-lg border border-white/20 bg-black/40 px-2 py-2 text-center font-display text-lg font-bold text-white"
                />
                <span className="text-xs text-white/60">分钟</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void saveDuration()}
                  className="rounded-full bg-lime-300 px-3 py-2 text-xs font-extrabold text-black disabled:opacity-50"
                >
                  保存
                </button>
              </div>
            )}
          </div>

          <div className="mt-6">
            <p className="text-center text-[12px] font-bold tracking-[0.14em] text-cyan-200">
              今日训练计划摘要
            </p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {(themes.length ? themes : [current.split_label || "训练"]).map((theme) => (
                <div
                  key={theme}
                  className="rounded-xl border border-cyan-300/25 bg-black/30 px-2 py-3 text-center"
                >
                  <div className="mx-auto grid h-10 w-10 place-items-center rounded-lg border border-cyan-200/30 bg-cyan-300/10 text-sm text-cyan-100">
                    {theme.slice(0, 1)}
                  </div>
                  <p className="mt-2 text-[11px] font-bold leading-tight text-white/85">
                    {MUSCLE_LABEL[theme] || theme}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {showDetail && (
            <div className="recap-panel mt-5 rounded-2xl border border-lime-300/30 bg-black/40 p-4 rise-in">
              <p className="text-[11px] font-bold tracking-[0.16em] text-lime-300">教练判断</p>
              <p className="mt-3 font-display text-[18px] font-bold leading-snug text-white">
                {busy
                  ? "正在重写这场…"
                  : line || "这场的教练总结还没出来。可以点下面再生成一次。"}
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => void regenerate()}
                className="pressable mt-4 w-full rounded-full border border-white/20 py-2.5 text-xs font-bold text-white/80 disabled:opacity-50"
              >
                {busy ? "生成中…" : "重新生成总结"}
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              if (!showDetail) setShowDetail(true);
              else setShowDetail(false);
            }}
            className="pressable mt-auto rounded-full bg-[#d6ff3a] py-3.5 font-display text-sm font-extrabold text-black shadow-[0_0_24px_rgba(214,255,58,0.35)]"
          >
            {showDetail ? "收起详细总结" : "查看详细总结"}
          </button>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  accent,
}: {
  label: string;
  value: string;
  unit: string;
  accent?: boolean;
}) {
  return (
    <div>
      <p className="text-[11px] text-white/55">{label}</p>
      <p className={`mt-1 font-display text-[28px] font-extrabold leading-none ${accent ? "text-lime-300" : "text-white"}`}>
        {value}
      </p>
      <p className="mt-1 text-[11px] text-white/45">{unit}</p>
    </div>
  );
}
