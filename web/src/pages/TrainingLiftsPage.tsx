import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Sparkline } from "../components/dashboard/TrainingDashboard";
import { MUSCLE_OPTIONS } from "../types";
import type { ExerciseStat } from "../types";

export function TrainingLiftsPage() {
  const navigate = useNavigate();
  const [muscle, setMuscle] = useState("全部");
  const { data: exercises = [], isLoading } = useQuery({
    queryKey: ["exercises"],
    queryFn: () => api<ExerciseStat[]>("/api/training/exercises"),
  });
  const shown = useMemo(() => {
    if (muscle === "全部") return exercises;
    return exercises.filter((item) => (item.muscle || "") === muscle);
  }, [exercises, muscle]);

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <h1 className="font-display text-[26px] font-bold tracking-tight">动作进阶</h1>

      <div className="no-scrollbar mt-4 flex gap-1.5 overflow-x-auto pb-1">
        {["全部", ...MUSCLE_OPTIONS].map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setMuscle(item)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-bold ${
              muscle === item ? "bg-accent text-accent-ink" : "border border-line bg-elevated text-muted"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {isLoading && <p className="mt-4 text-sm text-muted">加载中…</p>}
      {!isLoading && shown.length === 0 && (
        <p className="mt-4 text-sm text-muted">
          {exercises.length === 0 ? "完成一次训练后，这里会出现动作。" : `暂无「${muscle}」相关动作。`}
        </p>
      )}
      <ul className="mt-3 space-y-2">
        {shown.map((exercise) => {
          const isPr =
            exercise.last_weight != null &&
            exercise.best_weight != null &&
            exercise.last_weight >= exercise.best_weight;
          return (
            <li key={exercise.name}>
              <button
                type="button"
                onClick={() => navigate(`/training/exercise/${encodeURIComponent(exercise.name)}`)}
                className="pressable flex w-full items-center gap-3 rounded-2xl border border-line bg-elevated px-3.5 py-3 text-left"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="truncate font-display text-sm font-bold">{exercise.name}</p>
                    {isPr && (
                      <span className="rounded bg-ink px-1 py-0.5 text-[9px] font-extrabold text-accent">
                        PR
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[11px] text-muted">{exercise.muscle || "—"}</p>
                  <p className="font-num mt-1 text-xs font-bold">
                    上次 {exercise.last_weight != null ? `${exercise.last_weight}kg` : "自重"}
                    {exercise.last_reps != null ? ` × ${exercise.last_reps}` : ""}
                  </p>
                  {exercise.estimate_1rm != null && (
                    <p className="mt-0.5 text-[11px] text-muted">估算 1RM {exercise.estimate_1rm}kg</p>
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
