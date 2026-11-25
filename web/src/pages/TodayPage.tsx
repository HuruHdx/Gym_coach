import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createPortal } from "react-dom";
import { api, expandPlan, fetchFollowing, fetchPlanDetail, unfollowPlan } from "../lib/api";
import type {
  CardBlock,
  PlanBlockDetail,
  Profile,
  SetLog,
  TrainingDashboard,
  TrainingSession,
} from "../types";
import { WeightStepper } from "../components/WeightStepper";
import { RepsStepper } from "../components/RepsStepper";
import { ReorderItem, ReorderList } from "../components/ReorderList";
import { DraftCard } from "../components/DraftCard";
import { Sparkline } from "../components/dashboard/TrainingDashboard";
import {
  buildBlockRecoveryHint,
  buildMuscleGap,
  buildRestHints,
  lastCompletedReps,
  lastRepsForSet,
} from "../lib/todayHints";

const COACH_CHIPS = [
  { label: "今天只有\n30 分钟", prompt: "今天只有30分钟，帮我排一场高效训练" },
  { label: "练胸 ·\n器械优先", prompt: "今天练胸，器械优先" },
  { label: "按上次记录\n续排一场", prompt: "按我上次训练记录帮我续排今天这场" },
] as const;

const THUMB_TONES = [
  "from-[#cdbcf7] to-[#a98fe9]",
  "from-[#c9dcf8] to-[#96bdf1]",
  "from-[#c3ecd7] to-[#8fd6b4]",
  "from-[#f9d9c9] to-[#f0ad8d]",
  "from-[#f6c9e0] to-[#e793bd]",
];

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
  const [order, setOrder] = useState<string[]>([]);
  const orderRef = useRef<string[]>([]);
  orderRef.current = order;
  const [revising, setRevising] = useState(false);
  const [regenBusy, setRegenBusy] = useState(false);
  const [blockPickerOpen, setBlockPickerOpen] = useState(false);
  const [draft, setDraft] = useState<CardBlock | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  useEffect(() => {
    setLocal(session ?? null);
  }, [session]);
  useEffect(() => {
    setOrder([]);
  }, [session?.id]);
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

  const baseGroups = useMemo(() => groupByExercise(local?.sets || []), [local]);
  const groups = useMemo(() => sortGroups(baseGroups, order), [baseGroups, order]);
  useEffect(() => {
    if (pickedOpen) return;
    const firstOpen =
      groups.find((g) => g.sets.some((s) => !s.completed))?.name ?? groups[0]?.name ?? null;
    setOpenName(firstOpen);
  }, [groups, pickedOpen]);

  const { data: historySessions = [] } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=40"),
  });
  const { data: following } = useQuery({
    queryKey: ["plans-following"],
    queryFn: fetchFollowing,
  });

  const exerciseNames = useMemo(() => groups.map((g) => g.name), [groups]);
  const { data: resolvedThumbs } = useQuery({
    queryKey: ["exercise-resolve", exerciseNames.join("|")],
    queryFn: () =>
      api<{
        items: Record<string, { id?: string; name_zh?: string; thumb_url?: string | null }>;
      }>(`/api/exercises/resolve?names=${encodeURIComponent(exerciseNames.join(","))}`),
    enabled: exerciseNames.length > 0,
  });
  const thumbByName = useMemo(() => {
    const map = new Map<string, { thumb?: string | null; id?: string | null }>();
    for (const [name, item] of Object.entries(resolvedThumbs?.items || {})) {
      map.set(name, { thumb: item.thumb_url, id: item.id });
    }
    return map;
  }, [resolvedThumbs]);

  const currentGroup =
    groups.find((g) => g.sets.some((s) => !s.completed)) ?? groups[groups.length - 1] ?? null;
  const currentSet = currentGroup?.sets.find((s) => !s.completed) ?? null;
  const currentMeta = currentGroup ? thumbByName.get(currentGroup.name) : undefined;

  const { data: planForCues } = useQuery({
    queryKey: ["plan-detail-cues", local?.plan_template_id],
    queryFn: () => fetchPlanDetail(local!.plan_template_id!),
    enabled: Boolean(local?.plan_template_id) && local?.status === "active",
  });
  const planCue = useMemo(() => {
    if (!currentGroup || !planForCues) return null;
    const blocks = planForCues.blocks || [];
    const block =
      (local?.plan_block_id != null
        ? blocks.find((b) => b.id === local.plan_block_id)
        : null) ?? blocks[0];
    const row = block?.exercises?.find(
      (e) => (e.exercise_name || "").trim() === currentGroup.name.trim(),
    );
    const text = row?.cues_zh?.[0];
    return typeof text === "string" && text.trim() ? text.trim() : null;
  }, [currentGroup, planForCues, local?.plan_block_id]);

  const { data: currentDetail } = useQuery({
    queryKey: ["catalog-exercise-cue", currentMeta?.id],
    queryFn: () =>
      api<{ cues_zh?: string[]; id: string }>(
        `/api/exercises/${encodeURIComponent(currentMeta!.id!)}`,
      ),
    enabled: Boolean(currentMeta?.id) && local?.status === "active" && !planCue,
  });
  const currentCue = planCue || currentDetail?.cues_zh?.[0] || null;

  const prevReps = useMemo(() => {
    if (!currentGroup) return null;
    return lastCompletedReps(historySessions, currentGroup.name, local?.id);
  }, [historySessions, currentGroup, local?.id]);

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
        if (body.completed === true) {
          const name = prev.sets.find((s) => s.id === setId)?.exercise_name;
          const groupDone =
            Boolean(name) && sets.filter((s) => s.exercise_name === name).every((s) => s.completed);
          if (groupDone && name) {
            const ordered = sortGroups(groupByExercise(sets), orderRef.current);
            const next = ordered.find((group) => group.sets.some((s) => !s.completed));
            if (next) setOpenName(next.name);
          }
        }
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
    return <TodayIdleWorkbench />;
  }

  if (local.source === "rest" && local.status === "done") {
    return <TodayRestDone split={local.split_label} summary={local.summary} />;
  }

  const pct =
    local.progress.total > 0
      ? Math.round((local.progress.done / local.progress.total) * 100)
      : 0;
  const isDone = local.status === "done";
  const locked = isDone && !revising;
  const seconds = elapsedSeconds(local, now);
  const exerciseCount = groups.length;
  const isCoachPlan = local.plan_type === "custom" || (!local.plan_template_id && local.plan_type !== "framework" && local.plan_type !== "fixed");
  const sourceLine = buildSourceLine(local, following ?? null);
  const muscleSummary = [
    ...new Set(groups.map((g) => g.sets[0]?.muscle).filter(Boolean) as string[]),
  ]
    .slice(0, 4)
    .join(" · ");

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

  async function completeCurrentSet() {
    if (!currentSet || locked) return;
    const defaultReps = parseDefaultReps(currentSet.target_reps);
    const patch: Record<string, unknown> = { completed: true };
    if (currentSet.actual_reps == null) patch.actual_reps = defaultReps;
    if (currentSet.actual_weight == null && currentSet.target_weight != null) {
      patch.actual_weight = currentSet.target_weight;
    }
    try {
      await patchSet(currentSet.id, patch);
    } catch (e) {
      alert(String(e));
    }
  }

  const remainMoves = groups.filter((g) => g.sets.some((s) => !s.completed)).length;
  const allSetsDone =
    local.progress.total > 0 && local.progress.done >= local.progress.total;
  const outcomeLabel = local.session_outcome || (isDone ? "完成" : null);
  const dateLabel = formatTodayLabel();

  return (
    <div className="flex min-h-full flex-col px-5 pb-6 pt-4 rise-in">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Gym Coach</p>
      <div className="mt-1.5 flex items-start justify-between gap-3">
        <h1 className="font-display text-[28px] font-extrabold tracking-tight">今日</h1>
        {running && !isDone ? (
          <div className="text-right">
            <p className="text-[10px] font-bold tracking-wide text-muted">本场用时</p>
            <p className="font-num mt-0.5 text-[26px] font-extrabold leading-none tracking-tight">
              {formatClock(seconds)}
            </p>
            {/* 组次未打完时结束放次级；打完后主 CTA 在 Hero 里 */}
            {!allSetsDone ? (
              <button
                type="button"
                onClick={() => void completeSession()}
                className="pressable mt-1.5 rounded-lg border border-line bg-elevated/80 px-2.5 py-1 text-[11px] font-bold text-accent-text"
              >
                结束这场
              </button>
            ) : null}
          </div>
        ) : (
          <p className="pt-2 text-[12px] font-semibold text-muted">{dateLabel}</p>
        )}
      </div>

      {/* Hero：D 已完成 / C 训练中 / C′ 组次打完待收尾 / B 有计划未开练 */}
      <div className="mt-3 overflow-hidden rounded-[20px] border border-line bg-gradient-to-br from-[var(--hero-a)] via-[#f6f2fd] to-elevated p-4">
        <TodaySeg />

        {isDone ? (
          <>
            <p className="mt-3 text-[12px] font-semibold text-muted">
              {sourceLine} · 本场已结束
            </p>
            <div className="mt-1.5 flex items-start justify-between gap-2">
              <h2 className="font-display text-[26px] font-extrabold tracking-tight">
                {local.split_label || "训练"}
              </h2>
              <span className="mt-2 shrink-0 rounded-md bg-ok/15 px-2 py-1 text-[10px] font-bold text-ok">
                已完成
              </span>
            </div>
            <p className="mt-1.5 text-[12px] text-muted">
              <span className="num">
                {exerciseCount} 动作 · {local.progress.done} 组
                {local.duration_minutes != null && local.duration_minutes >= 1
                  ? ` · ${local.duration_minutes} 分钟`
                  : ""}
              </span>
            </p>
            {(local.summary || outcomeLabel) && (
              <>
                <div className="mt-2.5 flex items-center justify-between gap-2">
                  <p className="text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">
                    教练总结
                  </p>
                  {outcomeLabel && (
                    <span className="rounded-md bg-tint px-2 py-0.5 text-[10px] font-extrabold text-accent-text">
                      {outcomeLabel}
                    </span>
                  )}
                </div>
                {local.summary && (
                  <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink">
                    <HighlightedSummary text={local.summary} />
                  </p>
                )}
              </>
            )}
            <div className="mt-3 flex border-t border-line pt-3">
              <MiniStat label="完成组数" value={`${local.progress.done}`} unit="组" />
              <MiniStat
                label="训练时长"
                value={
                  local.duration_minutes != null && local.duration_minutes >= 1
                    ? String(local.duration_minutes)
                    : "—"
                }
                unit="分钟"
              />
              <MiniStat label="本场状态" value={outcomeLabel || "完成"} />
            </div>
            <Link to="/recap" className="mt-3.5 inline-block text-[12px] font-bold text-accent-text">
              查看完整总结和海报 ›
            </Link>
          </>
        ) : running && currentGroup && currentSet ? (
          <>
            <div className="mt-3.5 flex gap-3.5">
              <ThumbTile
                src={currentMeta?.thumb}
                tone={0}
                size="lg"
                onClick={() =>
                  currentMeta?.id &&
                  navigate(`/exercises/${encodeURIComponent(currentMeta.id)}`)
                }
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[21px] font-extrabold tracking-tight">
                  {currentGroup.name}
                </p>
                <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">
                  第{" "}
                  <b className="text-ink">
                    {currentSet.set_index} / {currentGroup.sets.length}
                  </b>{" "}
                  组 · 计划{" "}
                  <b className="text-ink">
                    {currentSet.target_weight != null ? `${currentSet.target_weight} kg` : "自重"} ×{" "}
                    {currentSet.target_reps || "—"}
                  </b>
                  {prevReps != null ? (
                    <>
                      <br />
                      上次 {prevReps} 次
                    </>
                  ) : null}
                </p>
              </div>
            </div>
            {currentCue && (
              <div className="mt-3 flex gap-2">
                <span className="shrink-0 pt-0.5 text-[10px] font-extrabold tracking-wide text-accent-text">
                  提示
                </span>
                <p className="text-[12px] leading-relaxed text-ink/90">{currentCue}</p>
              </div>
            )}
            {currentMeta?.id && (
              <button
                type="button"
                onClick={() => navigate(`/exercises/${encodeURIComponent(currentMeta.id!)}`)}
                className="mt-1.5 text-[11px] font-bold text-accent-text"
              >
                完整要领 · 常见错误 ›
              </button>
            )}
            <div className="mt-3.5 h-1 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-accent transition-all"
                style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
              />
            </div>
            <div className="mt-2 flex justify-between text-[11px] text-muted">
              <span className="num">
                {local.progress.done} / {local.progress.total} 组 · {pct}%
              </span>
              <span>还剩 {remainMoves} 个动作</span>
            </div>
            <button
              type="button"
              onClick={() => void completeCurrentSet()}
              className="pressable mt-3.5 flex w-full items-center justify-center rounded-[14px] bg-accent py-3.5 text-[15px] font-extrabold text-accent-ink"
            >
              完成这组
            </button>
          </>
        ) : allSetsDone || running ? (
          <>
            <p className="mt-3 text-[12px] font-semibold text-muted">
              {sourceLine} · {allSetsDone ? "组次已打完" : "今日进行中"}
            </p>
            <div className="mt-1.5 flex items-start justify-between gap-2">
              <h2 className="font-display text-[26px] font-extrabold tracking-tight">
                {local.split_label || "训练"}
              </h2>
              <span className="mt-2 shrink-0 rounded-md bg-ok/15 px-2 py-1 text-[10px] font-bold text-ok">
                {allSetsDone ? "待收尾" : "进行中"}
              </span>
            </div>
            <p className="mt-1.5 text-[12px] text-muted">
              <span className="num">
                {exerciseCount} 动作 · {local.progress.done} / {local.progress.total} 组
              </span>
              {muscleSummary ? ` · ${muscleSummary}` : ""}
            </p>
            <div className="mt-3.5 h-1 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-accent transition-all"
                style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
              />
            </div>
            <div className="mt-2 text-[11px] text-muted">
              {allSetsDone
                ? "本场组次都勾完了，点结束生成总结"
                : `还剩 ${remainMoves} 个动作 · 可在下方清单继续勾组`}
            </div>
            <button
              type="button"
              onClick={() => void completeSession()}
              className="pressable mt-3.5 w-full rounded-[14px] bg-accent py-3.5 text-[15px] font-extrabold text-accent-ink"
            >
              结束这场
            </button>
          </>
        ) : (
          <>
            <p className="mt-3 text-[12px] font-semibold text-muted">{sourceLine}</p>
            <div className="mt-1.5 flex items-start justify-between gap-2">
              <h2 className="font-display text-[26px] font-extrabold tracking-tight">
                {local.split_label || "训练"}
              </h2>
              <span className="mt-2 shrink-0 rounded-md bg-tint px-2 py-1 text-[10px] font-bold text-accent-text">
                今天
              </span>
            </div>
            <p className="mt-1.5 text-[12px] text-muted">
              {exerciseCount} 动作 · {local.progress.total} 组
              {muscleSummary ? ` · ${muscleSummary}` : ""}
            </p>
            {isCoachPlan && local.note ? (
              <p className="mt-2 text-[12px] leading-relaxed text-muted">
                「{local.note.length > 72 ? `${local.note.slice(0, 72)}…` : local.note}」
              </p>
            ) : null}
            <button
              type="button"
              disabled={timerBusy}
              onClick={() => void startTimer()}
              className="pressable mt-4 w-full rounded-[14px] bg-accent py-3.5 text-[15px] font-extrabold text-accent-ink disabled:opacity-50"
            >
              开始这场
            </button>
            {following?.active_plan_id ? (
              <button
                type="button"
                onClick={() => setBlockPickerOpen(true)}
                className="pressable mt-2.5 w-full rounded-[14px] border border-line bg-elevated/80 py-3 text-[13px] font-bold text-ink"
              >
                今天想练别的？
              </button>
            ) : isCoachPlan ? (
              <Link
                to="/coach"
                className="pressable mt-2.5 block w-full rounded-[14px] border border-line bg-elevated/80 py-3 text-center text-[13px] font-bold text-ink"
              >
                重新排 ›
              </Link>
            ) : null}
          </>
        )}
      </div>

      {blockPickerOpen && following?.active_plan_id && (
        <BlockPickerSheet
          planId={following.active_plan_id}
          currentBlockId={local.plan_block_id}
          onClose={() => setBlockPickerOpen(false)}
          onPicked={(card) => {
            setBlockPickerOpen(false);
            setDraft(card);
            setSheetOpen(true);
          }}
        />
      )}
      {draft && sheetOpen && (
        <TodayDraftSheet
          onClose={() => {
            setSheetOpen(false);
            setDraft(null);
          }}
        >
          <DraftCard
            card={draft}
            onChange={setDraft}
            todayStatus={isDone ? "done" : "active"}
            onAdopted={() => {
              void qc.invalidateQueries({ queryKey: ["training-today"] });
              void qc.invalidateQueries({ queryKey: ["plans-following"] });
              setSheetOpen(false);
              setDraft(null);
              void refetch();
            }}
          />
        </TodayDraftSheet>
      )}

      <div className="mt-3.5 flex items-center justify-between">
        <p className="text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">本场动作</p>
        {groups.length > 1 && !locked && (
          <button
            type="button"
            className="text-[11.5px] font-bold text-accent-text"
            onClick={() => {
              setPickedOpen(true);
              setOpenName(openName ? null : (groups[0]?.name ?? null));
            }}
          >
            排序 ›
          </button>
        )}
      </div>

      {groups.length > 1 && !locked ? (
        <ReorderList
          ids={groups.map((g) => g.name)}
          labelOf={(id) => id}
          onReorder={setOrder}
          className="divide-y divide-line border-t border-line"
        >
          {groups.map((g, idx) => (
            <ReorderItem key={g.name} id={g.name}>
              <FlatExerciseRow
                group={g}
                active={!isDone && currentGroup?.name === g.name}
                tone={idx % THUMB_TONES.length}
                thumb={thumbByName.get(g.name)?.thumb}
                exerciseId={thumbByName.get(g.name)?.id}
                open={openName === g.name}
                locked={locked}
                historySessions={historySessions}
                excludeSessionId={local.id}
                onToggle={() => {
                  setPickedOpen(true);
                  setOpenName(openName === g.name ? null : g.name);
                }}
                onPatch={patchSet}
              />
            </ReorderItem>
          ))}
        </ReorderList>
      ) : (
        <div className="divide-y divide-line border-t border-line">
          {groups.map((g, idx) => (
            <FlatExerciseRow
              key={g.name}
              group={g}
              active={!isDone && currentGroup?.name === g.name}
              tone={idx % THUMB_TONES.length}
              thumb={thumbByName.get(g.name)?.thumb}
              exerciseId={thumbByName.get(g.name)?.id}
              open={openName === g.name}
              locked={locked}
              historySessions={historySessions}
              excludeSessionId={local.id}
              onToggle={() => {
                setPickedOpen(true);
                setOpenName(openName === g.name ? null : g.name);
              }}
              onPatch={patchSet}
            />
          ))}
        </div>
      )}

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

      {isDone && !revising && (
        <div className="mt-5">
          <DoneNextHint />
          <button
            type="button"
            className="mt-3 w-full text-center text-xs font-bold text-muted underline"
            onClick={() => setRevising(true)}
          >
            记错了？修正本场记录
          </button>
        </div>
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

function DoneNextHint() {
  const { data: following } = useQuery({
    queryKey: ["plans-following"],
    queryFn: fetchFollowing,
  });
  const next = following?.week?.next_block;
  if (!following?.active_plan_id || !next) return null;
  return (
    <p className="mt-3 text-center text-[12px] text-muted">
      下次：<span className="font-bold text-ink">{next.title}</span>
      {(next.muscles || []).length > 0 ? ` · ${(next.muscles || []).join(" + ")}` : ""}
    </p>
  );
}

/** 状态 A / 跟练待开练：无今日 session */
function TodayIdleWorkbench() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<CardBlock | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [blockPickerOpen, setBlockPickerOpen] = useState(false);
  const [restBusy, setRestBusy] = useState(false);
  const [unfollowBusy, setUnfollowBusy] = useState(false);

  const followingQuery = useQuery({
    queryKey: ["plans-following"],
    queryFn: fetchFollowing,
  });
  const following = followingQuery.data;
  const nextBlock = following?.week?.next_block ?? null;
  const hasFollowReady = Boolean(following?.active_plan_id && nextBlock);
  const cycleDone = Boolean(following?.week?.week_cycle_done);

  const { data: profile } = useQuery({
    queryKey: ["profile"],
    queryFn: () => api<Profile>("/api/profile"),
  });
  const { data: weightHistory = [] } = useQuery({
    queryKey: ["weight-history"],
    queryFn: () => api<{ weight_kg: number; recorded_at: string }[]>("/api/profile/weight-history?limit=8"),
  });
  const { data: dashboard } = useQuery({
    queryKey: ["training-dashboard", "week"],
    queryFn: () => api<TrainingDashboard>("/api/training/dashboard?period=week"),
  });
  const { data: sessions = [] } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=40"),
  });

  const weightPoints = useMemo(
    () => weightHistory.map((p) => p.weight_kg).filter((n) => Number.isFinite(n)),
    [weightHistory],
  );
  const latestWeight =
    weightPoints.length > 0
      ? weightPoints[weightPoints.length - 1]
      : profile?.weight_kg ?? null;
  const weightDelta = useMemo(() => {
    if (weightPoints.length < 2) return null;
    return Math.round((weightPoints[weightPoints.length - 1] - weightPoints[0]) * 10) / 10;
  }, [weightPoints]);

  const trained = dashboard?.week.trained_days ?? 0;
  const target = dashboard?.week.target_days || profile?.days_per_week || 3;
  const prLift = (dashboard?.key_lifts || []).find((l) => l.is_pr) ?? dashboard?.key_lifts?.[0] ?? null;
  const muscleGap = useMemo(() => buildMuscleGap(dashboard?.muscle_pulse), [dashboard?.muscle_pulse]);
  const restHints = useMemo(
    () => buildRestHints(sessions, { targetDays: target, trainedDays: trained }),
    [sessions, target, trained],
  );
  const blockRecovery = useMemo(
    () =>
      hasFollowReady
        ? buildBlockRecoveryHint(nextBlock?.muscles, dashboard?.muscle_pulse)
        : null,
    [hasFollowReady, nextBlock?.muscles, dashboard?.muscle_pulse],
  );
  const musclesNeedRest = Boolean(blockRecovery && !blockRecovery.ready);
  const weekTargetMet = trained >= target && target > 0;
  /** 无跟练且达标 → 主推休息；跟练中肌群未恢复 / 本套已轮完也可记休息 */
  const suggestRestDay = weekTargetMet && !hasFollowReady;
  const showFollowRest =
    hasFollowReady && (musclesNeedRest || cycleDone || weekTargetMet);

  async function markRest() {
    if (restBusy) return;
    setRestBusy(true);
    try {
      await api<TrainingSession>("/api/training/rest-today", { method: "POST" });
      void qc.invalidateQueries({ queryKey: ["training-today"] });
      void qc.invalidateQueries({ queryKey: ["training-sessions"] });
      void qc.invalidateQueries({ queryKey: ["training-dashboard"] });
    } catch (e) {
      alert(String(e));
    } finally {
      setRestBusy(false);
    }
  }

  async function stopFollowing() {
    if (unfollowBusy) return;
    if (!confirm("先不跟这套了？只是不再推课，以前练过的记录都还在。")) return;
    setUnfollowBusy(true);
    try {
      await unfollowPlan();
      void qc.invalidateQueries({ queryKey: ["plans-following"] });
      void qc.invalidateQueries({ queryKey: ["profile"] });
    } catch (e) {
      alert(String(e));
    } finally {
      setUnfollowBusy(false);
    }
  }

  async function startNextBlock() {
    if (!following?.active_plan_id || !nextBlock || starting) return;
    setStarting(true);
    try {
      const res = await expandPlan(following.active_plan_id, nextBlock.id);
      setDraft(res.card);
      setSheetOpen(true);
    } catch (e) {
      alert(String(e));
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col px-5 pb-6 pt-4 rise-in">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Gym Coach</p>
      <div className="mt-1.5 flex items-start justify-between gap-3">
        <h1 className="font-display text-[28px] font-extrabold tracking-tight">今日</h1>
        <p className="pt-2 text-[12px] font-semibold text-muted">{formatTodayLabel()}</p>
      </div>

      <div className="mt-3 overflow-hidden rounded-[20px] border border-line bg-gradient-to-br from-[var(--hero-a)] via-[#f6f2fd] to-elevated p-4">
        <TodaySeg />

        {hasFollowReady && nextBlock ? (
          <>
            <p className="mt-3 text-[12px] font-semibold text-muted">
              {following?.plan?.title || "跟练计划"}
              {following?.week.progress_label ? ` · ${following.week.progress_label}` : ""}
              {cycleDone && (following?.week.total_blocks ?? 0) > 1 ? " · 可开下一轮" : ""}
            </p>
            <div className="mt-1.5 flex items-start justify-between gap-2">
              <h2 className="font-display text-[26px] font-extrabold tracking-tight">
                {nextBlock.title}
              </h2>
              <span className="mt-2 shrink-0 rounded-md bg-tint px-2 py-1 text-[10px] font-bold text-accent-text">
                今天
              </span>
            </div>
            <p className="mt-1.5 text-[12px] text-muted">
              {nextBlock.exercise_count ? (
                <>
                  <span className="num">{nextBlock.exercise_count}</span> 动作
                </>
              ) : (
                "—"
              )}
              {nextBlock.minutes_label ? (
                <>
                  {" · "}
                  <span className="num">{nextBlock.minutes_label}</span>
                </>
              ) : null}
              {(nextBlock.muscles || []).length > 0
                ? ` · ${(nextBlock.muscles || []).join(" · ")}`
                : ""}
            </p>
            {(nextBlock.preview_names || []).length > 0 && (
              <p className="mt-2 truncate text-[11.5px] text-muted">
                {(nextBlock.preview_names || []).slice(0, 4).join(" · ")}
              </p>
            )}
            {musclesNeedRest && blockRecovery?.text ? (
              <p className="mt-2 text-[12px] leading-relaxed text-muted">{blockRecovery.text}</p>
            ) : null}
            <div className="mt-4 flex flex-col gap-2.5">
              <button
                type="button"
                disabled={starting}
                onClick={() => void startNextBlock()}
                className="pressable flex w-full items-center justify-center gap-2 rounded-[14px] bg-accent py-3.5 text-[15px] font-extrabold text-accent-ink disabled:opacity-50"
              >
                {starting ? "展开中…" : "开始这场"}
              </button>
              <button
                type="button"
                onClick={() => setBlockPickerOpen(true)}
                className="pressable flex w-full items-center justify-center rounded-[14px] border border-line bg-elevated/80 py-3 text-[13px] font-bold text-ink"
              >
                今天想练别的？
              </button>
              {showFollowRest ? (
                <button
                  type="button"
                  disabled={restBusy}
                  onClick={() => void markRest()}
                  className="pressable flex w-full items-center justify-center rounded-[14px] border border-line bg-elevated/80 py-3 text-[13px] font-bold text-ink disabled:opacity-50"
                >
                  {restBusy ? "记录中…" : "记今天休息"}
                </button>
              ) : null}
              <div className="flex items-center justify-center gap-3 pt-0.5 text-[12px] font-semibold text-muted">
                <Link to="/plans" className="underline-offset-2 hover:underline">
                  换计划
                </Link>
                <span aria-hidden>·</span>
                <button
                  type="button"
                  disabled={unfollowBusy}
                  onClick={() => void stopFollowing()}
                  className="underline-offset-2 hover:underline disabled:opacity-50"
                >
                  {unfollowBusy ? "处理中…" : "先不跟了"}
                </button>
              </div>
            </div>
          </>
        ) : suggestRestDay ? (
          <>
            <IdleArt />
            <h2 className="text-center font-display text-[23px] font-extrabold tracking-tight">
              休息 · 建议
            </h2>
            <p className="mt-2 px-2.5 text-center text-[12.5px] leading-relaxed text-muted">
              这周够了，歇一天也行
              <br />
              本周 {trained} / {target} 练已达标
            </p>
            <div className="mt-4 flex flex-col gap-2.5">
              <button
                type="button"
                disabled={restBusy}
                onClick={() => void markRest()}
                className="pressable flex w-full items-center justify-center rounded-[14px] bg-accent py-3.5 text-[15px] font-extrabold text-accent-ink disabled:opacity-50"
              >
                {restBusy ? "记录中…" : "记今天休息"}
              </button>
              <Link
                to="/coach"
                className="pressable flex w-full items-center justify-center rounded-[14px] border border-line bg-elevated/80 py-3 text-[13px] font-bold text-ink"
              >
                还是想练 ›
              </Link>
            </div>
          </>
        ) : (
          <>
            <IdleArt />
            <h2 className="text-center font-display text-[23px] font-extrabold tracking-tight">
              今天还没有安排训练
            </h2>
            <p className="mt-2 px-2.5 text-center text-[12.5px] leading-relaxed text-muted">
              根据你的目标、伤痛和店里器械，
              <br />
              让 AI 排一场今天就能练的课
            </p>
            <div className="mt-4 flex flex-col gap-2.5">
              <Link
                to="/coach"
                className="pressable flex w-full items-center justify-center gap-2 rounded-[14px] bg-accent py-3.5 text-[15px] font-extrabold text-accent-ink"
              >
                AI 生成今日计划
                <span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-white/20">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" />
                  </svg>
                </span>
              </Link>
              <Link
                to="/plans"
                className="pressable flex w-full items-center justify-center rounded-[14px] border border-line bg-elevated/80 py-3 text-[13px] font-bold text-ink"
              >
                从热门计划挑选 ›
              </Link>
            </div>
          </>
        )}
      </div>

      {muscleGap && (
        <div className="mt-4 rounded-2xl border border-line bg-elevated px-3.5 py-3">
          <p className="text-[12.5px] font-extrabold text-ink">{muscleGap.headline}</p>
          <p className="mt-1 text-[11px] text-muted">{muscleGap.detail}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {muscleGap.rows.slice(0, 6).map((row) => (
              <span
                key={row.muscle}
                className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[10.5px] font-bold text-muted"
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${row.ready ? "bg-ok" : "bg-line"}`}
                  aria-hidden
                />
                {row.muscle} {row.days}d
              </span>
            ))}
          </div>
          {restHints.length > 0 && (
            <div className="mt-2 space-y-1">
              {restHints.map((h) => (
                <p key={h.text} className="text-[11.5px] font-semibold text-accent-text">
                  {h.text}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
      {!muscleGap && restHints.length > 0 && (
        <div className="mt-4 space-y-1">
          {restHints.map((h) => (
            <p key={h.text} className="text-[11.5px] font-semibold text-accent-text">
              {h.text}
            </p>
          ))}
        </div>
      )}

      {/* 身体数据 */}
      <div className="mt-4 flex items-center justify-between">
        <p className="text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">身体数据</p>
        <Link to="/me/settings" className="text-[11.5px] font-bold text-accent-text">
          编辑 ›
        </Link>
      </div>
      <div className="mt-2.5 flex gap-2">
        <div className="flex-1 rounded-2xl border border-line bg-elevated px-3 py-2.5">
          <p className="text-[10.5px] font-semibold text-muted">体重</p>
          <p className="font-num mt-1 text-[18px] font-extrabold tracking-tight">
            {latestWeight != null ? latestWeight.toFixed(1) : "—"}
            <small className="ml-0.5 text-[11px] font-semibold text-muted">kg</small>
          </p>
          {weightDelta != null ? (
            <p
              className={`mt-0.5 text-[10.5px] font-bold ${
                weightDelta < 0 ? "text-ok" : weightDelta > 0 ? "text-muted" : "text-muted"
              }`}
            >
              {weightDelta === 0
                ? "持平"
                : `${weightDelta > 0 ? "↑" : "↓"} ${Math.abs(weightDelta)} kg`}
            </p>
          ) : (
            <p className="mt-0.5 text-[10.5px] font-bold text-muted">去设置里记一笔</p>
          )}
          <div className="mt-1.5">
            <Sparkline values={weightPoints} />
          </div>
        </div>
        <div className="flex-1 rounded-2xl border border-line bg-elevated px-3 py-2.5">
          <p className="text-[10.5px] font-semibold text-muted">本周训练</p>
          <div className="mt-1 flex items-center gap-3">
            <BodyWeekRing trained={trained} target={target} />
            <div className="min-w-0">
              <p className="font-num text-[17px] font-extrabold">{trained} 场</p>
              <p className="mt-0.5 truncate text-[10.5px] text-muted">
                {prLift
                  ? `PR ${prLift.exercise_name.length > 4 ? prLift.exercise_name.slice(0, 4) : prLift.exercise_name} ${prLift.load}`
                  : `目标 ${target} 场`}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5">
        <p className="text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">推荐排课</p>
        <div className="mt-2.5 flex gap-2">
          {COACH_CHIPS.map((chip) => (
            <button
              key={chip.label}
              type="button"
              onClick={() => {
                try {
                  sessionStorage.setItem("coach_prefill", chip.prompt);
                } catch {
                  /* ignore */
                }
                navigate("/coach");
              }}
              className="pressable flex-1 rounded-xl border border-line bg-elevated px-1.5 py-2.5 text-center text-[11.5px] font-bold leading-snug text-ink"
            >
              {chip.label.split("\n").map((line) => (
                <span key={line} className="block">
                  {line}
                </span>
              ))}
            </button>
          ))}
        </div>
      </div>

      {draft && sheetOpen && (
        <TodayDraftSheet
          onClose={() => {
            setSheetOpen(false);
            setDraft(null);
          }}
        >
          <DraftCard
            card={draft}
            onChange={setDraft}
            todayStatus="none"
            onAdopted={() => {
              void qc.invalidateQueries({ queryKey: ["training-today"] });
              void qc.invalidateQueries({ queryKey: ["plans-following"] });
              setSheetOpen(false);
              setDraft(null);
            }}
          />
        </TodayDraftSheet>
      )}

      {blockPickerOpen && following?.active_plan_id && (
        <BlockPickerSheet
          planId={following.active_plan_id}
          currentBlockId={nextBlock?.id}
          onClose={() => setBlockPickerOpen(false)}
          onPicked={(card) => {
            setBlockPickerOpen(false);
            setDraft(card);
            setSheetOpen(true);
          }}
        />
      )}
    </div>
  );
}

function TodayRestDone({
  split,
  summary,
}: {
  split?: string | null;
  summary?: string | null;
}) {
  return (
    <div className="flex min-h-full flex-col px-5 pb-6 pt-4 rise-in">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Gym Coach</p>
      <div className="mt-1.5 flex items-start justify-between gap-3">
        <h1 className="font-display text-[28px] font-extrabold tracking-tight">今日</h1>
        <p className="pt-2 text-[12px] font-semibold text-muted">{formatTodayLabel()}</p>
      </div>
      <div className="mt-3 overflow-hidden rounded-[20px] border border-line bg-gradient-to-br from-[var(--hero-a)] via-[#f6f2fd] to-elevated p-4">
        <TodaySeg />
        <p className="mt-3 text-[12px] font-semibold text-muted">休息日</p>
        <h2 className="mt-1.5 font-display text-[26px] font-extrabold tracking-tight">
          {split || "休息"}
        </h2>
        <p className="mt-2 text-[12.5px] leading-relaxed text-muted">
          {summary || "今天记为休息日，不算进本周训练次数。"}
        </p>
        <Link
          to="/coach"
          className="pressable mt-4 inline-flex w-full items-center justify-center rounded-[14px] border border-line bg-elevated/80 py-3 text-[13px] font-bold text-ink"
        >
          还是想练 ›
        </Link>
      </div>
    </div>
  );
}

function BlockPickerSheet({
  planId,
  currentBlockId,
  onClose,
  onPicked,
}: {
  planId: string;
  currentBlockId?: number | null;
  onClose: () => void;
  onPicked: (card: CardBlock) => void;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["plan-detail", planId],
    queryFn: () => fetchPlanDetail(planId),
  });
  const blocks: PlanBlockDetail[] = data?.blocks || [];

  async function pick(blockId: number) {
    if (busyId != null) return;
    setBusyId(blockId);
    try {
      const res = await expandPlan(planId, blockId);
      onPicked(res.card);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusyId(null);
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[80] flex flex-col justify-end">
      <button
        type="button"
        aria-label="关闭"
        className="absolute inset-0 bg-scrim"
        onClick={onClose}
      />
      <div className="relative z-[1] max-h-[80dvh] overflow-y-auto rounded-t-2xl border border-line bg-bg px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />
        <div className="mb-3 flex items-center justify-between gap-2">
          <p className="text-xs font-bold text-muted">今天想练别的？选一个板块</p>
          <button type="button" className="text-xs font-bold text-accent-text" onClick={onClose}>
            关闭
          </button>
        </div>
        {isLoading && <p className="py-6 text-center text-sm text-muted">加载板块…</p>}
        <ul className="divide-y divide-line border-t border-line">
          {blocks.map((block) => {
            const active = block.id === currentBlockId;
            return (
              <li key={block.id}>
                <button
                  type="button"
                  disabled={busyId != null}
                  onClick={() => void pick(block.id)}
                  className="pressable flex w-full items-start gap-3 py-3 text-left disabled:opacity-50"
                >
                  <div className="min-w-0 flex-1">
                    <p className={`text-[14px] font-bold ${active ? "text-accent-text" : "text-ink"}`}>
                      {block.title}
                      {active ? " · 当前" : ""}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted">
                      {(block.muscles || []).join(" · ") || "—"}
                      {block.minutes_label ? ` · ${block.minutes_label}` : ""}
                      {block.exercises?.length ? ` · ${block.exercises.length} 动作` : ""}
                    </p>
                  </div>
                  <span className="shrink-0 pt-0.5 text-[12px] font-bold text-accent-text">
                    {busyId === block.id ? "…" : "选这个"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {!isLoading && blocks.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">这个计划还没有板块</p>
        )}
      </div>
    </div>,
    document.body,
  );
}

function buildSourceLine(
  session: TrainingSession,
  following: { plan?: { title?: string | null } | null; week?: { progress_label?: string | null; completed_count?: number; total_blocks?: number } } | null,
): string {
  if (session.plan_type === "custom" || (!session.plan_template_id && session.plan_type !== "framework" && session.plan_type !== "fixed")) {
    return "教练排的 · 按你今天的状态";
  }
  const title = following?.plan?.title;
  const progress =
    following?.week?.progress_label ||
    (following?.week?.total_blocks
      ? `第 ${Math.min((following.week.completed_count || 0) + 1, following.week.total_blocks)} 个板块`
      : null);
  if (title && progress) return `${title} · ${progress}`;
  if (title) return title;
  if (session.plan_type === "framework" || session.plan_type === "fixed") return "计划场次";
  return "今日计划";
}

function TodayDraftSheet({
  children,
  onClose,
}: {
  children: ReactNode;
  onClose: () => void;
}) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const id = window.requestAnimationFrame(() => setShown(true));
    return () => {
      document.body.style.overflow = prev;
      window.cancelAnimationFrame(id);
    };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-[80] flex flex-col justify-end">
      <button
        type="button"
        aria-label="关闭草稿"
        className={`absolute inset-0 bg-scrim transition-opacity duration-200 ${
          shown ? "opacity-100" : "opacity-0"
        }`}
        onClick={onClose}
      />
      <div
        className={`relative z-[1] max-h-[88dvh] overflow-y-auto rounded-t-2xl border border-line bg-bg px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 transition-transform duration-200 ${
          shown ? "translate-y-0" : "translate-y-full"
        }`}
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />
        <div className="mb-3 flex items-center justify-between gap-2">
          <p className="text-xs font-bold text-muted">今日草稿 · 可微调后采纳</p>
          <button type="button" className="text-xs font-bold text-accent-text" onClick={onClose}>
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

function FlatExerciseRow({
  group,
  active,
  tone,
  thumb,
  exerciseId,
  open,
  locked,
  historySessions,
  excludeSessionId,
  onToggle,
  onPatch,
}: {
  group: { name: string; muscle?: string | null; sets: SetLog[] };
  active: boolean;
  tone: number;
  thumb?: string | null;
  exerciseId?: string | null;
  open: boolean;
  locked: boolean;
  historySessions: TrainingSession[];
  excludeSessionId?: number | null;
  onToggle: () => void;
  onPatch: (id: number, body: Record<string, unknown>) => Promise<void>;
}) {
  const navigate = useNavigate();
  const doneCount = group.sets.filter((set) => set.completed).length;
  const allDone = doneCount === group.sets.length && group.sets.length > 0;
  const first = group.sets[0];
  const planHint = [
    group.muscle,
    first?.target_weight != null ? `${first.target_weight}kg` : null,
    first?.target_reps ? `${first.target_reps}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div>
      <div className="flex items-center gap-3 py-2">
        <button
          type="button"
          className="shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            if (exerciseId) navigate(`/exercises/${encodeURIComponent(exerciseId)}`);
          }}
          aria-label={`${group.name} 详情`}
        >
          <ThumbTile src={thumb} tone={tone} size="sm" />
        </button>
        <button type="button" onClick={onToggle} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          <div className="min-w-0 flex-1">
            <p className={`truncate text-[14px] font-bold ${active ? "text-accent-text" : "text-ink"}`}>
              {group.name}
            </p>
            {planHint ? <p className="mt-0.5 truncate text-[10.5px] text-muted">{planHint}</p> : null}
          </div>
          <span
            className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-extrabold ${
              allDone
                ? "bg-ok/15 text-ok"
                : active
                  ? "bg-tint text-accent-text"
                  : "border-[1.5px] border-line text-[#c6c1da]"
            }`}
          >
            {allDone ? "✓" : active ? String(doneCount || "·") : ""}
          </span>
          <span className="font-num w-8 shrink-0 text-right text-[12px] font-bold text-muted">
            {doneCount}/{group.sets.length}
          </span>
        </button>
      </div>
      {open && (
        <ul className="mb-2 space-y-1.5 border-t border-line/60 pb-2 pt-2">
          {group.sets.map((set) => (
            <SetRow
              key={set.id}
              set={set}
              disabled={locked}
              prevReps={lastRepsForSet(historySessions, group.name, set.set_index, excludeSessionId)}
              onPatch={onPatch}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function TodaySeg() {
  return (
    <div className="flex rounded-xl border border-white/90 bg-white/65 p-1">
      <span className="flex-1 rounded-[9px] bg-white py-2 text-center text-[13px] font-bold text-ink shadow-sm">
        训练
      </span>
      <span className="flex-1 rounded-[9px] py-2 text-center text-[13px] font-bold text-muted">
        饮食
      </span>
    </div>
  );
}

function ThumbTile({
  src,
  tone,
  size = "sm",
  onClick,
}: {
  src?: string | null;
  tone: number;
  size?: "sm" | "lg";
  onClick?: () => void;
}) {
  const dim = size === "lg" ? "h-14 w-14 rounded-2xl" : "h-9 w-9 rounded-[11px]";
  const grad = THUMB_TONES[tone % THUMB_TONES.length];
  const inner = src ? (
    <img src={src} alt="" className={`object-cover ${dim}`} />
  ) : (
    <div className={`grid place-items-center bg-gradient-to-br ${grad} ${dim}`}>
      <DumbbellIcon size={size === "lg" ? 28 : 18} />
    </div>
  );
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className="shrink-0 overflow-hidden">
        {inner}
      </button>
    );
  }
  return <div className="shrink-0 overflow-hidden">{inner}</div>;
}

function DumbbellIcon({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="white"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M6.5 6.5v11M17.5 6.5v11M4 9.5v5M20 9.5v5M6.5 12h11" />
    </svg>
  );
}

function MiniStat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="flex-1 border-l border-line pl-3 first:border-l-0 first:pl-0">
      <p className="text-[10px] font-semibold text-muted">{label}</p>
      <p className="font-num mt-0.5 text-[15px] font-extrabold">
        {value}
        {unit ? <small className="ml-0.5 text-[10px] font-semibold text-muted">{unit}</small> : null}
      </p>
    </div>
  );
}

function HighlightedSummary({ text }: { text: string }) {
  const parts = text.split(/(\d+(?:\.\d+)?\s*(?:kg|KG|次|组|分钟)|PR)/g);
  return (
    <>
      {parts.map((part, i) =>
        /^\d/.test(part) || part === "PR" ? (
          <b key={i} className="font-bold text-accent-text">
            {part}
          </b>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

function BodyWeekRing({ trained, target }: { trained: number; target: number }) {
  const pct = target > 0 ? Math.min(trained / target, 1) : 0;
  const R = 19;
  const C = 2 * Math.PI * R;
  const filled = C * pct;
  return (
    <div className="relative h-[42px] w-[42px] shrink-0">
      <svg width="42" height="42" viewBox="0 0 48 48" className="-rotate-90">
        <circle cx="24" cy="24" r={R} stroke="var(--line)" strokeWidth="5" fill="none" />
        <circle
          cx="24"
          cy="24"
          r={R}
          stroke="var(--accent)"
          strokeWidth="5"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${C - filled}`}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center font-num text-[11px] font-extrabold">
        {trained}/{target}
      </div>
    </div>
  );
}

function IdleArt() {
  return (
    <svg className="mx-auto mb-3.5 mt-1.5 h-[108px] w-[132px]" viewBox="0 0 132 108" fill="none" aria-hidden>
      <ellipse cx="66" cy="90" rx="40" ry="8" fill="var(--accent)" opacity=".08" />
      <circle cx="66" cy="46" r="34" fill="var(--accent)" opacity=".10" />
      <circle cx="66" cy="46" r="22" fill="var(--accent)" opacity=".10" />
      <path
        d="M46 46h40M53 38v16M46 41v10M79 41v10"
        stroke="var(--accent)"
        strokeWidth="3.5"
        strokeLinecap="round"
        opacity=".4"
      />
      <path
        d="M92 20l4-4M36 20l-4-4"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
        opacity=".25"
      />
    </svg>
  );
}

function formatTodayLabel(): string {
  const d = new Date();
  const week = ["日", "一", "二", "三", "四", "五", "六"][d.getDay()];
  return `${d.getMonth() + 1}月${d.getDate()}日 周${week}`;
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
  prevReps,
  onPatch,
}: {
  set: SetLog;
  disabled: boolean;
  prevReps?: number | null;
  onPatch: (id: number, body: Record<string, unknown>) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const defaultReps = useMemo(() => parseDefaultReps(set.target_reps), [set.target_reps]);
  const currentWeight = set.actual_weight ?? set.target_weight ?? null;
  const currentReps = set.actual_reps ?? defaultReps;

  async function toggle() {
    if (disabled) return;
    const nextCompleted = !set.completed;
    const patch: Record<string, unknown> = {
      completed: nextCompleted,
    };
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
      if (nextCompleted) setExpanded(false);
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
  const line = setLine(set, defaultReps);

  return (
    <li className={`rounded-lg border border-line/60 bg-bg/80 ${set.completed ? "opacity-80" : ""}`}>
      <div className="flex items-center gap-2 py-1 pl-2.5 pr-1">
        <button
          type="button"
          onClick={() => setExpanded((open) => !open)}
          className="min-w-0 flex-1 py-1.5 text-left"
        >
          <span className="text-sm font-bold text-ink">第 {set.set_index} 组</span>
          <span className="ml-2 font-num text-sm text-muted">{line}</span>
          {prevReps != null ? (
            <span className="ml-2 text-[11px] font-semibold text-muted">上次 {prevReps} 次</span>
          ) : null}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => void toggle()}
          className={`pressable h-10 shrink-0 rounded-full px-3.5 text-xs font-extrabold ${
            set.completed
              ? "border-2 border-accent-ink bg-accent text-accent-ink"
              : "border-2 border-line bg-elevated text-ink"
          } disabled:opacity-50`}
          aria-label={set.completed ? "取消完成本组" : "完成本组"}
        >
          {set.completed ? "✓" : "完成"}
        </button>
      </div>

      {expanded && (
        <div className="space-y-2 border-t border-line/40 px-2.5 py-2.5">
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
        </div>
      )}
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

function setLine(set: SetLog, defaultReps: number): string {
  const weight = set.completed ? (set.actual_weight ?? set.target_weight) : set.target_weight;
  const reps = set.completed
    ? set.actual_reps != null
      ? String(set.actual_reps)
      : set.target_reps || String(defaultReps)
    : set.target_reps || String(defaultReps);
  const weightText = weight != null && weight > 0 ? `${weight}kg` : "自重";
  return `${weightText} × ${reps}`;
}

function sortGroups<T extends { name: string }>(groups: T[], order: string[]): T[] {
  if (order.length === 0) return groups;
  const map = new Map(groups.map((group) => [group.name, group]));
  const picked = order.flatMap((name) => {
    const group = map.get(name);
    return group ? [group] : [];
  });
  const rest = groups.filter((group) => !order.includes(group.name));
  return [...picked, ...rest];
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
