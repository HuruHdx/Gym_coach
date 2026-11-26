import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { api } from "../lib/api";
import { WeightTrendChart } from "../components/dashboard/WeightTrendChart";
import type { ExerciseStat, SetLog, TrainingSession } from "../types";

export function ExerciseTrendPage() {
  const { name: raw = "" } = useParams();
  const name = decodeName(raw);
  const navigate = useNavigate();

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["training-sessions"],
    queryFn: () => api<TrainingSession[]>("/api/training/sessions?limit=50"),
  });
  const { data: exercises = [] } = useQuery({
    queryKey: ["exercises"],
    queryFn: () => api<ExerciseStat[]>("/api/training/exercises"),
  });

  const stat = exercises.find((e) => e.name === name) ?? null;
  const history = useMemo(() => exerciseHistory(sessions, name), [sessions, name]);
  const chartPoints = useMemo(
    () =>
      [...history]
        .reverse()
        .filter((p): p is HistPoint & { weight: number } => p.weight != null)
        .map((p) => ({ date: p.date, weight: p.weight, reps: p.reps })),
    [history],
  );

  const verdict = useMemo(() => buildVerdict(history, stat), [history, stat]);
  const advice = useMemo(() => buildAdvice(history), [history]);
  const isPr =
    stat?.last_weight != null &&
    stat?.best_weight != null &&
    Math.abs(stat.last_weight - stat.best_weight) < 0.01;

  return (
    <div className="flex min-h-full flex-col px-4 pb-8 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="pressable -ml-1 mb-1 inline-flex h-9 w-fit items-center gap-1 rounded-lg px-1 text-[13px] font-bold text-ink"
        aria-label="返回"
      >
        <ArrowLeft size={18} strokeWidth={2.25} />
        返回
      </button>

      <p className="text-[11px] font-bold text-muted">{stat?.muscle || "动作"}</p>
      <div className="mt-1 flex items-center gap-2">
        <h1 className="font-display text-[26px] font-extrabold tracking-tight">{name}</h1>
        {isPr && (
          <span className="rounded bg-ink px-1.5 py-0.5 text-[9px] font-extrabold text-[color:var(--accent-ink,#ece7fb)]">
            PR
          </span>
        )}
      </div>

      {verdict && (
        <div className="mt-3 rounded-2xl bg-tint px-4 py-3.5">
          <p className="text-[14px] font-extrabold leading-snug">{verdict.title}</p>
          {verdict.sub && (
            <p className="font-num mt-1 text-[11.5px] font-bold text-accent-text">{verdict.sub}</p>
          )}
        </div>
      )}

      {chartPoints.length > 0 && (
        <section className="mt-4">
          <p className="text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">重量走势</p>
          <div className="mt-2 rounded-2xl border border-line bg-elevated px-1 pb-2 pt-2">
            {isLoading ? (
              <p className="px-3 py-8 text-sm text-muted">加载中…</p>
            ) : (
              <WeightTrendChart points={chartPoints} />
            )}
          </div>
        </section>
      )}

      {advice && (
        <section className="mt-4 rounded-2xl border border-line bg-elevated px-4 py-3.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[12.5px] font-extrabold">本场之后怎么练</p>
            <span className="rounded border border-dashed border-line px-1.5 py-0.5 text-[9px] font-bold text-muted">
              规则建议
            </span>
          </div>
          <p className="font-num mt-2 text-[15px] font-extrabold">{advice.target}</p>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{advice.reason}</p>
        </section>
      )}

      <section className="mt-5">
        <p className="text-[12.5px] font-extrabold text-[color:var(--text-2,#54506b)]">每次做组</p>
        {history.length === 0 ? (
          <p className="mt-3 text-sm text-muted">完成并勾选组次后会出现在这里。</p>
        ) : (
          <ul className="mt-2 divide-y divide-line border-t border-line">
            {history.map((p, i) => {
              const prev = history[i + 1];
              const delta =
                p.weight != null && prev?.weight != null
                  ? Math.round((p.weight - prev.weight) * 10) / 10
                  : null;
              return (
                <li key={`${p.date}-${p.sessionId}`} className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-num text-sm font-bold">{p.date}</p>
                      <p className="mt-0.5 text-[11px] text-muted">
                        {p.split || "训练"} · {p.setsDone} 组
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-num text-sm font-extrabold">
                        {fmtWeight(p.weight)}
                        {p.reps != null ? ` × ${p.reps}` : ""}
                      </p>
                      {delta != null && delta !== 0 && (
                        <p className={`text-[11px] font-bold ${delta > 0 ? "text-ok" : "text-danger"}`}>
                          {delta > 0 ? `较上场 +${delta} kg` : `较上场 ${delta} kg`}
                        </p>
                      )}
                      {delta === 0 && <p className="text-[11px] text-muted">较上场持平</p>}
                    </div>
                  </div>
                  {p.sets.length > 0 && (
                    <p className="mt-2 font-num text-[12px] leading-relaxed text-ink/80">
                      {p.sets
                        .map((s) => {
                          const w = s.weight != null ? `${s.weight}kg` : "自重";
                          const r = s.reps != null ? `×${s.reps}` : "";
                          const f = s.feeling ? ` · ${s.feeling}` : "";
                          return `${w}${r}${f}`;
                        })
                        .join("  ·  ")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <Link
        to={`/exercises`}
        className="pressable mt-5 flex items-center justify-between border-t border-line py-3"
      >
        <div>
          <p className="text-[13.5px] font-bold">查看动作要领</p>
          <p className="mt-0.5 text-[10.5px] text-muted">发力提示、常见错误、示范图</p>
        </div>
        <ChevronRight size={16} className="text-muted/50" />
      </Link>
    </div>
  );
}

function buildVerdict(history: HistPoint[], stat: ExerciseStat | null) {
  if (history.length === 0) return null;
  const latest = history[0];
  const prev = history[1];
  const best = stat?.best_weight;
  if (prev?.weight != null && latest.weight != null) {
    const delta = Math.round((latest.weight - prev.weight) * 10) / 10;
    if (delta > 0) {
      return {
        title: "稳步加重，状态在上升",
        sub: `${prev.weight} → ${latest.weight} kg · 较上场 +${delta} kg${
          best != null ? ` · 个人最好 ${best} kg` : ""
        }`,
      };
    }
    if (delta < 0) {
      return {
        title: "本场略有回落，先稳住再加",
        sub: `${prev.weight} → ${latest.weight} kg · 较上场 ${delta} kg`,
      };
    }
    return {
      title: "重量持平，巩固动作质量",
      sub: `维持 ${latest.weight} kg${best != null ? ` · 个人最好 ${best} kg` : ""}`,
    };
  }
  return {
    title: "已有记录，继续积累对比",
    sub:
      latest.weight != null
        ? `最近 ${latest.weight} kg${latest.reps != null ? ` × ${latest.reps}` : ""}`
        : null,
  };
}

function buildAdvice(history: HistPoint[]) {
  if (history.length < 2) {
    return {
      target: "先再练 1–2 场",
      reason: "记录还不够，暂不硬凑加重建议；下次把组次勾齐，方便对比。",
    };
  }
  const latest = history[0];
  if (latest.weight == null || latest.reps == null) {
    return {
      target: "维持当前安排",
      reason: "最近一场没有完整重量/次数，先按原计划完成。",
    };
  }
  const feeling = latest.sets.map((s) => s.feeling).find(Boolean);
  const hard = feeling === "力竭" || feeling === "勉强";
  const easy = feeling === "轻松";
  const repsOk = latest.reps >= 8;

  if (!hard && easy && repsOk) {
    const next = Math.round((latest.weight + 2.5) * 10) / 10;
    return {
      target: `${next} kg × ${latest.reps} · 建议 ${latest.setsDone || 3} 组`,
      reason: `上次 ${latest.reps} 次完成且体感轻松，可尝试 +2.5kg；若动作变形或次数掉到 6 以下，退回 ${latest.weight} kg。`,
    };
  }
  return {
    target: `${latest.weight} kg × ${latest.reps} · 建议维持`,
    reason: hard
      ? "上次体感偏累，先维持重量把次数做稳。"
      : "次数或体感未到加重点，维持当前负荷即可。",
  };
}

function decodeName(raw: string) {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function fmtWeight(w: number | null | undefined) {
  if (w == null) return "自重";
  return `${w} kg`;
}

type HistSet = { weight: number | null; reps: number | null; feeling?: string | null };
type HistPoint = {
  sessionId: number;
  date: string;
  split: string | null;
  weight: number | null;
  reps: number | null;
  setsDone: number;
  sets: HistSet[];
};

function exerciseHistory(sessions: TrainingSession[], name: string): HistPoint[] {
  const rows: HistPoint[] = [];
  for (const s of sessions) {
    if (s.status !== "done" && s.status !== "active") continue;
    const sets = s.sets.filter((x) => x.exercise_name === name && x.completed);
    if (!sets.length) continue;
    const weight = bestWeight(sets);
    const bestSet =
      weight == null ? sets[0] : sets.find((x) => x.actual_weight === weight) || sets[0];
    rows.push({
      sessionId: s.id,
      date: s.session_date.slice(5),
      split: s.split_label ?? null,
      weight,
      reps: bestSet.actual_reps ?? parseReps(bestSet.target_reps),
      setsDone: sets.length,
      sets: sets.map((x) => ({
        weight: x.actual_weight ?? x.target_weight ?? null,
        reps: x.actual_reps ?? parseReps(x.target_reps),
        feeling: x.feeling ?? null,
      })),
    });
  }
  return rows;
}

function parseReps(raw: string | null | undefined): number | null {
  if (raw == null || raw === "") return null;
  const m = String(raw).match(/(\d+)/);
  return m ? Number(m[1]) : null;
}

function bestWeight(sets: SetLog[]) {
  let best: number | null = null;
  for (const set of sets) {
    const w = set.actual_weight ?? set.target_weight;
    if (w == null) continue;
    if (best == null || w > best) best = w;
  }
  return best;
}
