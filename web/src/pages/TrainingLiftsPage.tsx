import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { api } from "../lib/api";
import { Sparkline } from "../components/dashboard/TrainingDashboard";
import { MUSCLE_OPTIONS } from "../types";
import type { ExerciseStat } from "../types";

type TrendFilter = "全部" | "进步" | "持平" | "回落" | "新练";
type SortKey = "recent" | "1rm" | "progress";

const TREND_CHIPS: TrendFilter[] = ["全部", "进步", "持平", "回落", "新练"];

export function TrainingLiftsPage() {
  const navigate = useNavigate();
  const [muscle, setMuscle] = useState("全部");
  const [trend, setTrend] = useState<TrendFilter>("全部");
  const [sort, setSort] = useState<SortKey>("recent");
  const [sortOpen, setSortOpen] = useState(false);

  const { data: exercises = [], isLoading } = useQuery({
    queryKey: ["exercises"],
    queryFn: () => api<ExerciseStat[]>("/api/training/exercises"),
  });

  const shown = useMemo(() => {
    let list = exercises;
    if (muscle !== "全部") list = list.filter((item) => (item.muscle || "") === muscle);
    if (trend !== "全部") {
      list = list.filter((item) => matchTrend(item, trend));
    }
    const sorted = [...list];
    if (sort === "1rm") {
      sorted.sort((a, b) => (b.estimate_1rm || 0) - (a.estimate_1rm || 0));
    } else if (sort === "progress") {
      sorted.sort((a, b) => trendScore(b) - trendScore(a));
    }
    // recent: keep API order (typically recent-first)
    return sorted;
  }, [exercises, muscle, trend, sort]);

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate("/training")}
        className="pressable -ml-1 mb-1 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
      >
        <ChevronLeft size={16} />
        训练
      </button>
      <h1 className="font-display text-[26px] font-extrabold tracking-tight">动作进阶</h1>
      <p className="mt-1 text-[12px] text-muted">我练过的动作 · 重量趋势与估算 1RM</p>

      <div className="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto pb-1">
        {["全部", ...MUSCLE_OPTIONS.filter((m) => m !== "全身")].map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setMuscle(item)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-[11.5px] font-bold ${
              muscle === item
                ? "bg-ink text-[color:var(--accent-ink,#fff)]"
                : "border border-line bg-elevated text-muted"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="mt-2 flex items-center gap-1.5">
        <div className="no-scrollbar flex min-w-0 flex-1 gap-1.5 overflow-x-auto">
          {TREND_CHIPS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setTrend(item)}
              className={`shrink-0 rounded-md px-2.5 py-1 text-[10.5px] font-bold ${
                trend === item
                  ? "border border-[color-mix(in_srgb,var(--accent)_35%,transparent)] bg-tint text-accent-text"
                  : "border border-line bg-elevated text-muted"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={() => setSortOpen((v) => !v)}
            className="pressable rounded-md border border-line bg-elevated px-2.5 py-1 text-[10.5px] font-bold text-muted"
          >
            {sort === "recent" ? "最近训练" : sort === "1rm" ? "1RM 最高" : "进步最快"} ▾
          </button>
          {sortOpen && (
            <div className="absolute right-0 z-10 mt-1 w-28 overflow-hidden rounded-lg border border-line bg-bg shadow-lg">
              {(
                [
                  ["recent", "最近训练"],
                  ["1rm", "1RM 最高"],
                  ["progress", "进步最快"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    setSort(key);
                    setSortOpen(false);
                  }}
                  className={`block w-full px-3 py-2 text-left text-[11px] font-bold ${
                    sort === key ? "bg-tint text-accent-text" : "text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {isLoading && <p className="mt-4 text-sm text-muted">加载中…</p>}
      {!isLoading && shown.length === 0 && (
        <p className="mt-8 text-center text-sm text-muted">
          {exercises.length === 0 ? "完成一次训练后，这里会出现动作。" : "没有符合筛选的动作。"}
        </p>
      )}

      <ul className="mt-3 divide-y divide-line border-t border-line">
        {shown.map((exercise) => {
          const isPr =
            exercise.last_weight != null &&
            exercise.best_weight != null &&
            Math.abs(exercise.last_weight - exercise.best_weight) < 0.01;
          return (
            <li key={exercise.name}>
              <button
                type="button"
                onClick={() => navigate(`/training/exercise/${encodeURIComponent(exercise.name)}`)}
                className="pressable flex w-full items-center gap-3 py-2.5 text-left"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="truncate text-[13.5px] font-bold">{exercise.name}</p>
                    {isPr && (
                      <span className="rounded bg-ink px-1 py-0.5 text-[9px] font-extrabold text-[color:var(--accent-ink,#ece7fb)]">
                        PR
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[10.5px] text-muted">{exercise.muscle || "—"}</p>
                  <p className="font-num mt-1 text-[12px] font-bold">
                    上次 {exercise.last_weight != null ? `${exercise.last_weight} kg` : "自重"}
                    {exercise.last_reps != null ? ` × ${exercise.last_reps}` : ""}
                  </p>
                  {exercise.estimate_1rm != null && (
                    <p className="mt-0.5 text-[10.5px] text-muted">估算 1RM {exercise.estimate_1rm} kg</p>
                  )}
                </div>
                <Sparkline values={exercise.history} />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function matchTrend(item: ExerciseStat, filter: TrendFilter) {
  const t = item.trend || "→";
  if (filter === "进步") return t === "↑";
  if (filter === "回落") return t === "↓";
  if (filter === "持平") return t === "→" && (item.history?.length || 0) >= 2;
  if (filter === "新练") return (item.history?.length || 0) < 2;
  return true;
}

function trendScore(item: ExerciseStat) {
  const hist = item.history || [];
  if (hist.length < 2) return -999;
  return hist[hist.length - 1] - hist[0];
}
