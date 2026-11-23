import { useEffect, useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DraftCard } from "../components/DraftCard";
import { LoopClip } from "../components/LoopClip";
import {
  api,
  expandPlan,
  fetchPlanDetail,
  followPlan,
  unfollowPlan,
} from "../lib/api";
<<<<<<< HEAD
import { feedbackError, toast } from "../feedback";
import type { CardBlock, PlanBlockDetail, TrainingSession } from "../types";
=======
import type { CardBlock, PlanBlockDetail, PlanExerciseRow, TrainingSession } from "../types";
>>>>>>> 8ac665dff4450761d8f30170231d0d37b36598d6

export function PlanDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [activeBlockId, setActiveBlockId] = useState<number | null>(null);
  const [draft, setDraft] = useState<CardBlock | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);

  const detailQuery = useQuery({
    queryKey: ["plan-detail", id],
    queryFn: () => fetchPlanDetail(id),
    enabled: Boolean(id),
  });

  const { data: todaySession } = useQuery({
    queryKey: ["training-today"],
    queryFn: () => api<TrainingSession | null>("/api/training/today"),
  });

  const todayStatus: "none" | "active" | "done" = !todaySession
    ? "none"
    : todaySession.status === "done"
      ? "done"
      : todaySession.status === "active"
        ? "active"
        : "none";

  const plan = detailQuery.data;
  const blocks = useMemo(() => plan?.blocks ?? [], [plan]);
  const activeBlock = useMemo(
    () => blocks.find((block) => block.id === activeBlockId) ?? null,
    [blocks, activeBlockId],
  );
  const isFollowing = Boolean(plan?.is_following);

  const totalExercises = useMemo(
    () => blocks.reduce((sum, block) => sum + block.exercises.length, 0),
    [blocks],
  );

  useEffect(() => {
    if (!draft) setSheetOpen(false);
  }, [draft]);

<<<<<<< HEAD
  async function startBlock(block: PlanBlockDetail) {
    if (!id || expandingId != null) return;
    setExpandingId(block.id);
    try {
      const res = await expandPlan(id, block.id);
      setDraft(res.card);
      setSheetOpen(true);
    } catch (e) {
      toast.err(feedbackError(e));
    } finally {
      setExpandingId(null);
    }
  }

=======
>>>>>>> 8ac665dff4450761d8f30170231d0d37b36598d6
  async function toggleFollow() {
    if (!id || followBusy) return;
    if (isFollowing) {
      if (!confirm("退出跟练？本周进度标签会清空，已打卡记录仍保留。")) return;
    }
    setFollowBusy(true);
    try {
      if (isFollowing) await unfollowPlan();
      else await followPlan(id);
      void qc.invalidateQueries({ queryKey: ["plan-detail", id] });
      void qc.invalidateQueries({ queryKey: ["plans-following"] });
      toast.ok(isFollowing ? "已退出跟练" : "已加入跟练");
    } catch (e) {
      toast.err(feedbackError(e));
    } finally {
      setFollowBusy(false);
    }
  }

  async function adoptBlock(block: PlanBlockDetail) {
    if (!id || expanding) return;
    setExpanding(true);
    try {
      const res = await expandPlan(id, block.id);
      setDraft(res.card);
      setSheetOpen(true);
    } catch (e) {
      alert(String(e));
    } finally {
      setExpanding(false);
    }
  }

  if (detailQuery.isLoading) {
    return <div className="px-4 pt-8 text-sm text-muted">加载计划…</div>;
  }

  if (detailQuery.isError || !plan) {
    return (
      <div className="flex min-h-full flex-col px-4 pb-6 pt-3">
        <button
          type="button"
          onClick={() => navigate("/plans")}
          className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
        >
          <ChevronLeft size={16} />
          计划库
        </button>
        <p className="mt-6 text-sm text-danger">计划不存在或未发布。</p>
      </div>
    );
  }

<<<<<<< HEAD
  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate("/plans")}
        className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
      >
        <ChevronLeft size={16} />
        计划列表
      </button>

      <div
        className="relative overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-[var(--hero-a)] via-bg to-bg p-4"
        style={
          plan.cover_url
            ? {
                backgroundImage: `linear-gradient(to top, rgb(var(--bg-rgb) / 0.94), rgb(var(--bg-rgb) / 0.4)), url(${plan.cover_url})`,
                backgroundSize: "cover",
                backgroundPosition: "center",
              }
            : undefined
        }
      >
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-md bg-tint px-2 py-0.5 text-[10px] font-extrabold text-accent-text">
            {plan.badge_label || plan.scene_tag || "计划"}
          </span>
          {plan.scene_tag && (
            <span className="rounded-md border border-line bg-elevated/80 px-2 py-0.5 text-[10px] font-bold text-muted">
              {plan.scene_tag}
            </span>
          )}
          {plan.level_label && (
            <span className="rounded-md border border-line bg-elevated/80 px-2 py-0.5 text-[10px] font-bold text-muted">
              {plan.level_label}
            </span>
          )}
          {isFollowing && (
            <span className="rounded-md bg-ok/15 px-2 py-0.5 text-[10px] font-extrabold text-ok">
              跟练中
            </span>
          )}
        </div>
        <h1 className="mt-4 font-display text-[26px] font-extrabold tracking-tight">{plan.title}</h1>
        {plan.author && <p className="mt-1 text-[12px] text-muted">{plan.author}</p>}
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted">
          <span className="num">每周 {plan.days_per_week} 练</span>
          {plan.minutes_label && <span className="num">{plan.minutes_label}</span>}
          <span className="num">{blocks.length} 个板块</span>
          {isFollowing && week?.progress_label && (
            <span className="num font-bold text-accent-text">{week.progress_label}</span>
          )}
        </div>

        <button
          type="button"
          disabled={followBusy}
          onClick={() => void toggleFollow()}
          className={`pressable mt-4 w-full rounded-md py-2.5 text-[13px] font-extrabold disabled:opacity-50 ${
            isFollowing
              ? "border border-line bg-elevated/90 text-ink"
              : "bg-accent text-accent-ink"
          }`}
        >
          {followBusy
            ? "处理中…"
            : isFollowing
              ? "跟练中 · 退出"
              : multiBlock
                ? "加入跟练"
                : "加入跟练 · 单日计划"}
        </button>
        {!multiBlock && !isFollowing && (
          <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
            单日模板也可设为当前跟练，方便今日页记住你在练哪套。
          </p>
=======
  if (activeBlock) {
    const sets = activeBlock.exercises.reduce((sum, ex) => sum + (ex.target_sets || 0), 0);
    return (
      <div className="flex min-h-full flex-col pb-[calc(96px+env(safe-area-inset-bottom))] pt-3 rise-in">
        <div className="px-4">
          <button
            type="button"
            onClick={() => setActiveBlockId(null)}
            className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
          >
            <ChevronLeft size={16} />
            {plan.title}
          </button>
          <h1 className="font-display text-[24px] font-extrabold tracking-tight">{activeBlock.title}</h1>
          <p className="mt-1 font-num text-[12px] text-muted">
            {activeBlock.exercises.length} 动作
            {sets > 0 ? ` · ${sets} 组` : ""}
            {activeBlock.minutes_label ? ` · ${activeBlock.minutes_label}` : ""}
          </p>
        </div>

        <ul className="mt-4 divide-y divide-line border-t border-line px-4">
          {activeBlock.exercises.map((ex) => (
            <ExerciseRow key={ex.id} exercise={ex} />
          ))}
        </ul>

        <div className="fixed bottom-0 left-0 right-0 z-30 mx-auto max-w-md border-t border-line bg-bg/95 px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 backdrop-blur-sm">
          <button
            type="button"
            disabled={expanding}
            onClick={() => void adoptBlock(activeBlock)}
            className="pressable w-full rounded-xl bg-accent py-3 text-sm font-extrabold text-accent-ink disabled:opacity-60"
          >
            {expanding ? "展开中…" : "采纳为今日计划"}
          </button>
          <p className="mt-2 text-center text-[10.5px] text-muted">
            采纳后可在草稿里调组数/重量/动作，只影响今天这场
          </p>
        </div>

        {draft && sheetOpen && (
          <DraftSheet
            onClose={() => {
              setSheetOpen(false);
              setDraft(null);
            }}
          >
            <DraftCard
              card={draft}
              onChange={setDraft}
              todayStatus={todayStatus}
              onAdopted={() => {
                void qc.invalidateQueries({ queryKey: ["training-today"] });
                void qc.invalidateQueries({ queryKey: ["training-sessions"] });
                void qc.invalidateQueries({ queryKey: ["training-dashboard"] });
                setSheetOpen(false);
                setDraft(null);
                navigate("/");
              }}
            />
          </DraftSheet>
>>>>>>> 8ac665dff4450761d8f30170231d0d37b36598d6
        )}
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col pb-[calc(96px+env(safe-area-inset-bottom))] pt-3 rise-in">
      <div className="px-4">
        <button
          type="button"
          onClick={() => navigate("/plans")}
          className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
        >
          <ChevronLeft size={16} />
          计划库
        </button>

        <div
          className="relative overflow-hidden rounded-[18px] p-4 text-white"
          style={
            plan.cover_url
              ? {
                  backgroundImage: `linear-gradient(165deg, rgba(23,22,28,.25) 0%, rgba(23,22,28,.88) 75%), url(${plan.cover_url})`,
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                }
              : { background: "linear-gradient(165deg, #342c46 0%, #17161c 72%)" }
          }
        >
          <div className="flex flex-wrap gap-1.5">
            {plan.scene_tag && <CoverTag label={plan.scene_tag} />}
            {plan.level_label && <CoverTag label={plan.level_label} />}
            {plan.badge_label && <CoverTag label={plan.badge_label} />}
          </div>
          <h1 className="mt-10 font-display text-[26px] font-extrabold tracking-tight">{plan.title}</h1>
        </div>

        <div className="mt-3 flex gap-4 font-num text-[13px] font-extrabold">
          <span>
            {blocks.length}
            <small className="ml-0.5 text-[10px] font-semibold text-muted">板块</small>
          </span>
          <span>
            {totalExercises}
            <small className="ml-0.5 text-[10px] font-semibold text-muted">动作</small>
          </span>
          {plan.minutes_label && (
            <span>
              {plan.minutes_label.replace(/^约\s*/, "")}
              <small className="ml-0.5 text-[10px] font-semibold text-muted">/场</small>
            </span>
          )}
        </div>

        {(plan.description || plan.split_summary) && (
          <p className="mt-3 text-[13px] leading-relaxed text-muted">
            {plan.description || plan.split_summary}
          </p>
        )}

        <div className="mt-3 flex flex-wrap gap-1.5">
          {(plan.muscle_tags || []).map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-line bg-elevated px-2.5 py-1 text-[10.5px] font-bold text-muted"
            >
              {tag}
            </span>
          ))}
          {(plan.gear_tags || []).map((tag) => (
            <span
              key={`g-${tag}`}
              className="rounded-full border border-line bg-bg px-2.5 py-1 text-[10.5px] font-bold text-muted"
            >
              {tag}
            </span>
          ))}
        </div>

        <p className="mb-1 mt-5 text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">
          训练板块
        </p>
      </div>

      <div className="divide-y divide-line border-t border-line">
        {blocks.map((block, index) => {
          const sets = block.exercises.reduce((sum, ex) => sum + (ex.target_sets || 0), 0);
          return (
            <button
              key={block.id}
              type="button"
              onClick={() => setActiveBlockId(block.id)}
              className="pressable flex w-full items-center gap-3 px-4 py-3 text-left"
            >
              <span className="font-num grid h-7 w-7 shrink-0 place-items-center rounded-full bg-tint text-[12px] font-extrabold text-accent-text">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-bold">{block.title}</p>
                <p className="mt-0.5 text-[11px] text-muted">
                  {block.exercises.length} 个动作
                  {sets > 0 ? ` · ${sets} 组` : ""}
                  {block.minutes_label ? ` · ${block.minutes_label}` : ""}
                </p>
              </div>
              <ChevronRight size={16} className="shrink-0 text-muted/50" />
            </button>
          );
        })}
      </div>

      <div className="fixed bottom-0 left-0 right-0 z-30 mx-auto max-w-md border-t border-line bg-bg/95 px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 backdrop-blur-sm">
        <button
          type="button"
          disabled={followBusy}
          onClick={() => void toggleFollow()}
          className={`pressable w-full rounded-xl py-3 text-sm font-extrabold disabled:opacity-60 ${
            isFollowing ? "border border-line bg-elevated text-ink" : "bg-accent text-accent-ink"
          }`}
        >
          {followBusy ? "处理中…" : isFollowing ? "跟练中 · 点击退出" : "加入跟练"}
        </button>
        <p className="mt-2 text-center text-[10.5px] text-muted">
          跟练进度与状态在「我的计划」里查看，本页只展示计划本身
        </p>
      </div>
    </div>
  );
}

function CoverTag({ label }: { label: string }) {
  return (
    <span className="rounded-md bg-white/16 px-2 py-0.5 text-[10px] font-bold text-white">
      {label}
    </span>
  );
}

function ExerciseRow({ exercise }: { exercise: PlanExerciseRow }) {
  const name = exercise.exercise_name || "待补充";
  const detailPath = exercise.exercise_id
    ? `/exercises/${encodeURIComponent(exercise.exercise_id)}`
    : null;
  const inner = (
    <>
      <div className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-xl bg-tint text-[10px] font-bold text-accent-text">
        {exercise.thumb_url ? (
          <LoopClip src={exercise.thumb_url} className="h-full w-full object-cover" lazy />
        ) : (
          name.slice(0, 2)
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="truncate text-[13.5px] font-bold">{name}</p>
          {!!exercise.warmup_sets && (
            <span className="rounded border border-dashed border-line px-1.5 py-0.5 text-[9px] font-bold text-muted">
              热身 {exercise.warmup_sets} 组
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[10.5px] text-muted">
          {[exercise.target_muscle, exercise.role_label || exercise.role].filter(Boolean).join(" · ") ||
            "—"}
        </p>
      </div>
      <div className="shrink-0 text-right">
        {exercise.target_sets != null && (
          <p className="font-num text-[12px] font-extrabold">{exercise.target_sets} 组</p>
        )}
        {exercise.target_reps && (
          <p className="mt-0.5 text-[10.5px] text-muted">{exercise.target_reps} 次</p>
        )}
      </div>
      {detailPath && <ChevronRight size={16} className="shrink-0 text-muted/50" />}
    </>
  );

  if (detailPath) {
    return (
      <li>
        <Link to={detailPath} className="pressable flex items-center gap-3 py-3">
          {inner}
        </Link>
      </li>
    );
  }
  return <li className="flex items-center gap-3 py-3">{inner}</li>;
}

function DraftSheet({
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
        className={`relative z-[1] max-h-[88dvh] overflow-y-auto rounded-t-2xl border border-line bg-bg px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 shadow-lg transition-transform duration-200 ${
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
