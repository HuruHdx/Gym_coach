import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { SetLog, TrainingSession } from "../types";
import { WeightStepper } from "../components/WeightStepper";
import { RepsStepper } from "../components/RepsStepper";

export function TodayPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: session, isLoading, refetch } = useQuery({
    queryKey: ["training-today"],
    queryFn: () => api<TrainingSession | null>("/api/training/today"),
  });

  const [local, setLocal] = useState<TrainingSession | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [timerBusy, setTimerBusy] = useState(false);
  const [needMinutes, setNeedMinutes] = useState(false);
  const [minuteDraft, setMinuteDraft] = useState("45");
  const [openName, setOpenName] = useState<string | null>(null);
  const [pickedOpen, setPickedOpen] = useState(false);
  const [revising, setRevising] = useState(false);
  const [regenBusy, setRegenBusy] = useState(false);
  useEffect(() => {
    setLocal(session ?? null);
  }, [session]);
  useEffect(() => {
    // 新一场 / 仍在执行中：退出修正态
    if (session?.status !== "done") setRevising(false);
  }, [session?.id, session?.status]);

  const running = Boolean(local?.timer_started_at) && local?.status === "active";
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);

  const groups = useMemo(() => groupByExercise(local?.sets || []), [local]);
  useEffect(() => {
    if (pickedOpen) return;
    const firstOpen =
      groups.find((g) => g.sets.some((s) => !s.completed))?.name ?? groups[0]?.name ?? null;
    setOpenName(firstOpen);
  }, [groups, pickedOpen]);

  const patchSet = useCallback(
    async (setId: number, body: Record<string, unknown>) => {
      // 乐观更新：+/- 立刻反映在 UI，再等接口确认
      setLocal((prev) => {
        if (!prev) return prev;
        const sets = prev.sets.map((s) => {
          if (s.id !== setId) return s;
          return {
            ...s,
            ...(Object.prototype.hasOwnProperty.call(body, "completed")
              ? { completed: Boolean(body.completed) }
              : {}),
            ...(Object.prototype.hasOwnProperty.call(body, "actual_weight")
              ? { actual_weight: (body.actual_weight as number | null) ?? null }
              : {}),
            ...(Object.prototype.hasOwnProperty.call(body, "actual_reps")
              ? { actual_reps: (body.actual_reps as number | null) ?? null }
              : {}),
            ...(Object.prototype.hasOwnProperty.call(body, "feeling")
              ? { feeling: (body.feeling as string | null) ?? null }
              : {}),
            ...(Object.prototype.hasOwnProperty.call(body, "note")
              ? { note: (body.note as string | null) ?? null }
              : {}),
          };
        });
        const done = sets.filter((s) => s.completed).length;
        return { ...prev, sets, progress: { done, total: sets.length } };
      });
      try {
        const updated = await api<SetLog>(`/api/training/sets/${setId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        setLocal((prev) => {
          if (!prev) return prev;
          const sets = prev.sets.map((s) => (s.id === setId ? updated : s));
          const done = sets.filter((s) => s.completed).length;
          return { ...prev, sets, progress: { done, total: sets.length } };
        });
        void qc.invalidateQueries({ queryKey: ["training-sessions"] });
      } catch (e) {
        void refetch();
        throw e;
      }
    },
    [qc, refetch],
  );

  async function startTimer() {
    if (!local || timerBusy || local.status === "done" || local.timer_started_at) return;
    setTimerBusy(true);
    try {
      const next = await api<TrainingSession>(`/api/training/sessions/${local.id}/timer`, {
        method: "POST",
        body: JSON.stringify({ action: "start" }),
      });
      setLocal(next);
      qc.setQueryData(["training-today"], next);
      setNow(Date.now());
    } catch (e) {
      alert(String(e));
    } finally {
      setTimerBusy(false);
    }
  }

  async function completeSession(manualMinutes?: number, forceAsIs?: boolean) {
    if (!local) return;
    const elapsed = elapsedSeconds(local, Date.now());
    const clockMinutes = Math.floor(elapsed / 60);

    // 没开计时（0分）或计时过短（<3分钟），且用户未显式确认补充或强制直接完成
    if (manualMinutes == null && !forceAsIs && clockMinutes < 3) {
      setNeedMinutes(true);
      return;
    }
    if (manualMinutes != null && (manualMinutes < 1 || manualMinutes > 300)) {
      alert("时长填 1 到 300 分钟");
      return;
    }
    if (
      manualMinutes == null &&
      !forceAsIs &&
      !confirm("标记本次训练完成？计时会记进这场，实际重量写入上次记忆。")
    ) {
      return;
    }
    try {
      const done = await api<TrainingSession>(`/api/training/sessions/${local.id}/complete`, {
        method: "POST",
        body: JSON.stringify(
          manualMinutes != null ? { duration_minutes: manualMinutes } : {},
        ),
      });
      setLocal(done);
      qc.invalidateQueries({ queryKey: ["training-today"] });
      qc.invalidateQueries({ queryKey: ["training-sessions"] });
      qc.invalidateQueries({ queryKey: ["training-dashboard"] });
      qc.invalidateQueries({ queryKey: ["exercises"] });
      navigate("/recap");
    } catch (e) {
      alert(String(e));
    }
  }

  if (isLoading) {
    return <div className="px-4 pt-8 text-sm text-muted">加载今日…</div>;
  }

  if (!local || local.status === "abandoned") {
    return (
      <div className="flex min-h-full flex-col px-4 pb-4 pt-3 rise-in">
        <p className="font-display text-[11px] font-extrabold uppercase tracking-[0.12em] text-muted">
          Gym Coach
        </p>
        <h1 className="font-display text-[26px] font-bold tracking-tight">今日</h1>
        <div className="relative mt-4 flex min-h-[52vh] flex-1 flex-col overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-[var(--hero-a)] via-bg to-bg p-5">
          <p className="text-[11px] font-bold uppercase tracking-widest text-muted">Ready</p>
          <h2 className="font-display relative mt-3 max-w-[10ch] text-3xl font-extrabold leading-none tracking-tight">
            还没开始
          </h2>
          <p className="relative mt-3 max-w-[28ch] text-sm leading-relaxed text-muted">
            去教练页定制一版草稿，采纳后回到这里专心打卡。
          </p>
          <Link
            to="/coach"
            className="pressable relative mt-auto inline-flex w-full items-center justify-center rounded-md bg-accent py-3.5 font-display text-sm font-extrabold text-accent-ink"
          >
            呼叫 AI 教练定制
          </Link>
        </div>
      </div>
    );
  }

  const pct =
    local.progress.total > 0
      ? Math.round((local.progress.done / local.progress.total) * 100)
      : 0;
  const isDone = local.status === "done";
  const locked = isDone && !revising;
  const seconds = elapsedSeconds(local, now);

  async function regenerateSummary() {
    if (!local || regenBusy) return;
    setRegenBusy(true);
    try {
      const done = await api<TrainingSession>(`/api/training/sessions/${local.id}/complete`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setLocal(done);
      setRevising(false);
      void qc.invalidateQueries({ queryKey: ["training-today"] });
      void qc.invalidateQueries({ queryKey: ["training-sessions"] });
      void qc.invalidateQueries({ queryKey: ["training-dashboard"] });
      void qc.invalidateQueries({ queryKey: ["exercises"] });
    } catch (e) {
      alert(String(e));
    } finally {
      setRegenBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <p className="font-display text-[11px] font-extrabold uppercase tracking-[0.12em] text-muted">
        Gym Coach
      </p>
      <div className="flex items-end justify-between gap-3">
        <h1 className="font-display text-[26px] font-bold tracking-tight">
          今日
          <em className="ml-2 text-base font-semibold not-italic text-muted">
            {local.split_label || "训练"}
          </em>
        </h1>
        <span
          className={`rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${
            isDone ? "bg-ok/15 text-ok" : "bg-accent/40 text-accent-ink"
          }`}
        >
          {isDone ? "已完成" : "执行中"}
        </span>
      </div>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted">
        {local.progress.done}/{local.progress.total} 组 · {pct}%
        {isDone && !revising ? " · 已锁定，展开可回看" : ""}
        {revising ? " · 修正中，改完请重新生成总结" : ""}
      </p>

      {!isDone && (
        <div className="mt-4 rounded-xl border border-line bg-elevated px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-bold tracking-wide text-muted">训练计时</p>
              <p className="font-display text-3xl font-extrabold tabular-nums">{formatClock(seconds)}</p>
            </div>
            {!running ? (
              <button
                type="button"
                disabled={timerBusy}
                onClick={() => void startTimer()}
                className="pressable rounded-md bg-accent px-4 py-2 text-sm font-extrabold text-accent-ink disabled:opacity-50"
              >
                开始训练
              </button>
            ) : (
              <span className="rounded-md bg-ok/15 px-3 py-1.5 text-xs font-bold text-ok">计时中</span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted">点开始就计时，点完成结束。组间休息不用管。</p>
        </div>
      )}

      {isDone && (
        <p className="mt-3 text-xs text-muted">
          训练时长{" "}
          {local.duration_minutes != null && local.duration_minutes >= 1
            ? `${local.duration_minutes} 分钟`
            : "还没记"}
          。结算页可以改。
        </p>
      )}

      <div className="mt-4 flex items-center justify-between gap-2">
        <p className="text-xs font-bold text-muted">动作列表 ({groups.length})</p>
        {groups.length > 1 && (
          <button
            type="button"
            className="text-xs font-bold text-accent underline"
            onClick={() => {
              setPickedOpen(true);
              setOpenName(openName ? null : (groups[0]?.name ?? null));
            }}
          >
            {openName ? "全部收起" : "展开首项"}
          </button>
        )}
      </div>

      <div className="mt-2 space-y-2.5">
        {groups.map((g) => {
          const doneCount = g.sets.filter((s) => s.completed).length;
          const allDone = doneCount === g.sets.length && g.sets.length > 0;
          const open = openName === g.name;
          return (
            <div
              key={g.name}
              className="overflow-hidden rounded-xl border border-line bg-elevated transition-colors"
            >
              <button
                type="button"
                onClick={() => {
                  setPickedOpen(true);
                  setOpenName(open ? null : g.name);
                }}
                className="flex w-full items-center justify-between px-3.5 py-3 text-left transition-colors hover:bg-bg/40 active:bg-bg/60"
              >
                <div className="flex items-center gap-2">
                  <span className="font-display text-base font-bold text-ink">{g.name}</span>
                  {g.muscle && (
                    <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] font-bold text-muted">
                      {g.muscle}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                      allDone ? "bg-ok/15 text-ok" : "bg-bg text-muted"
                    }`}
                  >
                    {doneCount}/{g.sets.length} 组
                  </span>
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`text-muted transition-transform duration-200 ${
                      open ? "rotate-180" : ""
                    }`}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </button>
              {open && (
                <ul className="space-y-2 border-t border-line px-3.5 pb-3.5 pt-2.5">
                  {g.sets.map((s) => (
                    <SetRow key={s.id} set={s} disabled={locked} onPatch={patchSet} />
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      {!isDone && needMinutes && (
        <div className="mt-6 rounded-xl border border-line bg-elevated p-4">
          <p className="text-sm font-bold">
            {Math.floor(elapsedSeconds(local, Date.now()) / 60) < 1
              ? "未开启计时，是否补充实际训练时长？"
              : `本次计时仅 ${Math.floor(elapsedSeconds(local, Date.now()) / 60)} 分钟，是否补充实际时长？`}
          </p>
          <p className="mt-1 text-xs text-muted">
            若中途才开启计时或忘了点开始，可在此补充完整时长，方便后续准确计算消耗热量。
          </p>
          <div className="mt-3 flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={300}
              inputMode="numeric"
              value={minuteDraft}
              onChange={(e) => setMinuteDraft(e.target.value)}
              className="w-24 rounded-md border border-line bg-bg px-3 py-2 font-display text-lg font-bold"
            />
            <span className="text-sm text-muted">分钟</span>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                const n = Number(minuteDraft);
                if (!Number.isFinite(n) || n < 1 || n > 300) {
                  alert("时长填 1 到 300 分钟");
                  return;
                }
                void completeSession(Math.round(n));
              }}
              className="pressable flex-1 rounded-md bg-accent py-2.5 font-display text-sm font-extrabold text-accent-ink"
            >
              补充时长并完成
            </button>
            <button
              type="button"
              onClick={() => void completeSession(undefined, true)}
              className="pressable rounded-md border border-line bg-bg px-3 py-2.5 text-xs font-bold text-muted hover:text-ink"
            >
              先不补，直接完成
            </button>
          </div>
        </div>
      )}

      {!isDone && (
        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            onClick={() => void completeSession()}
            className="pressable w-full rounded-md bg-accent py-3.5 font-display text-sm font-extrabold text-accent-ink"
          >
            完成训练 · 写入记忆
          </button>
          <button
            type="button"
            className="text-xs font-bold text-muted underline"
            onClick={() => refetch()}
          >
            刷新
          </button>
        </div>
      )}

      {isDone && !revising && (
        <>
          <Link
            to="/recap"
            className="pressable mt-6 block overflow-hidden rounded-2xl bg-ink p-5 text-bg"
          >
            <p className="text-[11px] font-extrabold uppercase tracking-[0.2em] text-accent">Done</p>
            <h2 className="mt-2 font-display text-2xl font-extrabold">今日总结已生成</h2>
            <p className="mt-2 text-sm text-bg/70">点开看教练对这场的判断。</p>
            <p className="mt-4 text-sm font-bold text-accent">查看结算 →</p>
          </Link>
          <button
            type="button"
            className="mt-3 w-full text-center text-xs font-bold text-muted underline"
            onClick={() => setRevising(true)}
          >
            记错了？修正本场记录
          </button>
        </>
      )}

      {isDone && revising && (
        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            disabled={regenBusy}
            onClick={() => void regenerateSummary()}
            className="pressable w-full rounded-md bg-accent py-3.5 font-display text-sm font-extrabold text-accent-ink disabled:opacity-50"
          >
            {regenBusy ? "正在重新生成…" : "重新生成总结"}
          </button>
          <button
            type="button"
            className="text-xs font-bold text-muted underline"
            onClick={() => setRevising(false)}
          >
            取消修正
          </button>
        </div>
      )}
    </div>
  );
}

function parseDefaultReps(targetReps?: string | null): number {
  if (!targetReps) return 10;
  const cleaned = targetReps.replace(/[^0-9-~至到]/g, "");
  const matchRange = cleaned.match(/(\d+)[-~至到](\d+)/);
  if (matchRange) {
    return parseInt(matchRange[2], 10);
  }
  const matchNum = cleaned.match(/(\d+)/);
  if (matchNum) {
    return parseInt(matchNum[1], 10);
  }
  return 10;
}

function SetRow({
  set,
  disabled,
  onPatch,
}: {
  set: SetLog;
  disabled: boolean;
  onPatch: (id: number, body: Record<string, unknown>) => Promise<void>;
}) {
  const defaultReps = useMemo(() => parseDefaultReps(set.target_reps), [set.target_reps]);
  const currentWeight = set.actual_weight ?? set.target_weight ?? null;
  const currentReps = set.actual_reps ?? defaultReps;

  async function toggle() {
    if (disabled) return;
    const nextCompleted = !set.completed;
    const patch: Record<string, unknown> = {
      completed: nextCompleted,
    };
    // 首次打勾时，自动填入计划的目标重量和目标次数
    if (nextCompleted) {
      if (set.actual_reps == null) {
        patch.actual_reps = defaultReps;
      }
      if (set.actual_weight == null && set.target_weight != null) {
        patch.actual_weight = set.target_weight;
      }
    }
    try {
      await onPatch(set.id, patch);
    } catch (e) {
      alert(String(e));
    }
  }

  async function handleWeightChange(newVal: number | null) {
    try {
      await onPatch(set.id, { actual_weight: newVal });
    } catch (e) {
      alert(String(e));
    }
  }

  async function handleRepsChange(newReps: number) {
    try {
      await onPatch(set.id, { actual_reps: newReps });
    } catch (e) {
      alert(String(e));
    }
  }

  async function handleNote(text: string) {
    try {
      await onPatch(set.id, { note: text.trim() || null });
    } catch (e) {
      alert(String(e));
    }
  }

  async function handleFeeling(feeling: string) {
    if (disabled) return;
    const nextFeeling = set.feeling === feeling ? null : feeling;
    try {
      await onPatch(set.id, { feeling: nextFeeling });
    } catch (e) {
      alert(String(e));
    }
  }

  const planWeight = set.target_weight != null ? `${set.target_weight}kg` : "自重";
  const planReps = set.target_reps || "8-10次";

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-line/60 bg-bg/80 px-2.5 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="font-semibold text-ink">第 {set.set_index} 组</div>
        <button
          type="button"
          disabled={disabled}
          onClick={toggle}
          className={`pressable inline-flex items-center gap-1.5 rounded-md border-[1.5px] px-2 py-1 text-[11px] font-bold ${
            set.completed
              ? "border-accent-ink bg-accent text-accent-ink"
              : "border-line bg-elevated text-ink"
          } disabled:opacity-50`}
        >
          <span
            className={`grid h-4 w-4 place-items-center rounded-sm border text-[10px] ${
              set.completed ? "border-accent-ink" : "border-ink/40"
            }`}
          >
            {set.completed ? "✓" : ""}
          </span>
          {set.completed ? "已完成本组" : "完成本组"}
        </button>
      </div>

      <div className="grid grid-cols-[3rem_1fr] items-center gap-x-2 gap-y-2 text-xs">
        <span className="text-[11px] font-bold text-muted">计划</span>
        <span className="text-[12px] text-ink">
          {planWeight} × {planReps}
        </span>
        <span className="text-[11px] font-bold text-muted">实际</span>
        <div className="flex flex-wrap items-center gap-1.5">
          <WeightStepper
            value={currentWeight}
            step={2.5}
            disabled={disabled}
            label={`${set.exercise_name} 第${set.set_index}组重量`}
            onChange={handleWeightChange}
          />
          <RepsStepper
            value={currentReps}
            defaultValue={defaultReps}
            disabled={disabled}
            label={`${set.exercise_name} 第${set.set_index}组次数`}
            onChange={handleRepsChange}
          />
        </div>
      </div>

      <label className="block text-[11px] text-muted">
        这组感受
        <input
          key={set.note ?? ""}
          defaultValue={set.note ?? ""}
          disabled={disabled}
          placeholder="例如：很轻松，可以加重"
          className="mt-1 w-full rounded-md border border-line bg-elevated px-2 py-1.5 text-xs text-ink outline-none placeholder:text-muted"
          onBlur={(e) => {
            const next = e.target.value.trim();
            if (next === (set.note ?? "")) return;
            void handleNote(next);
          }}
        />
      </label>

      <div className="border-t border-line/40 pt-2">
        <p className="text-[11px] text-muted">这组重量感觉，可选</p>
        <div className="mt-1.5 grid grid-cols-3 gap-1.5">
          {[
            { id: "轻松", label: "轻松" },
            { id: "合适", label: "合适" },
            { id: "力竭", label: "力竭" },
          ].map((f) => {
            const active = set.feeling === f.id;
            return (
              <button
                key={f.id}
                type="button"
                disabled={disabled}
                onClick={() => handleFeeling(f.id)}
                className={`pressable rounded-md border py-1.5 text-xs font-bold ${
                  active
                    ? f.id === "力竭"
                      ? "border-rose-500 bg-rose-500 text-white"
                      : f.id === "轻松"
                        ? "border-emerald-600 bg-emerald-600 text-white"
                        : "border-ink bg-ink text-bg"
                    : "border-line bg-elevated text-ink"
                } disabled:opacity-50`}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </div>
    </li>
  );
}

function elapsedSeconds(session: TrainingSession, now: number): number {
  let total = session.duration_seconds ?? 0;
  if (session.timer_started_at && session.status === "active") {
    const start = Date.parse(session.timer_started_at);
    if (!Number.isNaN(start)) total += Math.max(0, Math.floor((now - start) / 1000));
  }
  return total;
}

function formatClock(seconds: number): string {
  const safe = Math.max(0, seconds);
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = safe % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function groupByExercise(sets: SetLog[]) {
  const map = new Map<string, { name: string; muscle?: string | null; sets: SetLog[] }>();
  for (const s of sets) {
    const g = map.get(s.exercise_name) || {
      name: s.exercise_name,
      muscle: s.muscle,
      sets: [],
    };
    g.sets.push(s);
    map.set(s.exercise_name, g);
  }
  return [...map.values()];
}
