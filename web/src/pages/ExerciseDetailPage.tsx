import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { LoopClip } from "../components/LoopClip";
import { api } from "../lib/api";
import type { TrainingSession } from "../types";

type Slot = { role: string; url: string | null };

type CatalogDetail = {
  id: string;
  name_zh: string;
  name_en: string | null;
  muscle: string | null;
  sub_region: string | null;
  movement_pattern: string | null;
  gear: string | null;
  modality: string | null;
  coach_core: boolean;
  joint_stress: Record<string, string>;
  instructions_zh: string[];
  cues_zh: string[];
  common_mistakes_zh: string[];
  aliases: string[];
  slots: Slot[];
};

const JOINT_LABELS: Record<string, string> = {
  waist: "腰",
  knee: "膝",
  shoulder: "肩",
  wrist: "腕",
  elbow: "肘",
};

const LEVEL_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

function isVideo(url: string) {
  return /\.(mp4|webm|mov)(\?|$)/i.test(url);
}

export function ExerciseDetailPage() {
  const { id: raw = "" } = useParams();
  const id = decodeURIComponent(raw);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [frame, setFrame] = useState<"start" | "end">("start");
  const [adding, setAdding] = useState(false);
  const [addMsg, setAddMsg] = useState("");
  const [addErr, setAddErr] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["catalog-exercise", id],
    queryFn: () => api<CatalogDetail>(`/api/exercises/${encodeURIComponent(id)}`),
    enabled: Boolean(id),
  });

  const slotMap = useMemo(() => {
    const map: Record<string, string | null> = {};
    for (const slot of data?.slots ?? []) map[slot.role] = slot.url;
    return map;
  }, [data]);

  const demoUrl = slotMap.demo;
  const startUrl = slotMap.start;
  const endUrl = slotMap.end;
  const canFlip = Boolean(startUrl && endUrl && !demoUrl);

  useEffect(() => {
    if (!canFlip) return;
    const timer = window.setInterval(() => {
      setFrame((prev) => (prev === "start" ? "end" : "start"));
    }, 1200);
    return () => window.clearInterval(timer);
  }, [canFlip, id]);

  useEffect(() => {
    setFrame("start");
    setAddMsg("");
    setAddErr("");
  }, [id]);

  const mediaUrl = demoUrl || (frame === "end" ? endUrl : startUrl) || startUrl || endUrl;
  const tags = [
    data?.muscle,
    data?.sub_region,
    data?.movement_pattern,
    data?.gear,
    data?.modality,
  ].filter(Boolean) as string[];

  const risks = Object.entries(data?.joint_stress || {})
    .filter(([, level]) => level && level !== "low")
    .map(([joint, level]) => `${JOINT_LABELS[joint] || joint} ${LEVEL_LABELS[level] || level}`);

  function goBack() {
    if (window.history.length > 1) navigate(-1);
    else navigate("/exercises");
  }

  async function addToToday() {
    if (!data) return;
    setAdding(true);
    setAddMsg("");
    setAddErr("");
    try {
      await api<TrainingSession>("/api/training/today/add-exercise", {
        method: "POST",
        body: JSON.stringify({ exercise_id: data.id, sets: 3, reps: "8-12" }),
      });
      setAddMsg("已加入今日 · 3 组");
      void qc.invalidateQueries({ queryKey: ["training-today"] });
      void qc.invalidateQueries({ queryKey: ["training-sessions"] });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "加入失败";
      if (msg.includes("409") || msg.includes("已完成")) {
        setAddErr("今日训练已完成。如需再练，请到教练页重新采纳计划。");
      } else {
        setAddErr(msg.replace(/^\d+:\s*/, "") || "加入失败");
      }
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col pb-[calc(88px+env(safe-area-inset-bottom))] pt-3">
      <div className="px-4">
        <button
          type="button"
          onClick={goBack}
          className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
        >
          <ChevronLeft size={16} />
          返回
        </button>
      </div>

      {isLoading && <p className="px-4 text-sm text-muted">加载中…</p>}
      {isError && <p className="px-4 text-sm text-danger">动作加载失败或不存在。</p>}

      {data && (
        <>
          <div className="mx-4 overflow-hidden rounded-2xl border border-line bg-elevated">
            <div className="relative aspect-square bg-bg">
              {mediaUrl ? (
                isVideo(mediaUrl) && demoUrl ? (
                  <LoopClip
                    src={mediaUrl}
                    poster={startUrl || endUrl || undefined}
                    className="h-full w-full object-contain"
                  />
                ) : isVideo(mediaUrl) ? (
                  <video
                    src={mediaUrl}
                    poster={startUrl || endUrl || undefined}
                    className="h-full w-full object-contain"
                    controls
                    playsInline
                  />
                ) : (
                  <img
                    key={mediaUrl}
                    src={mediaUrl}
                    alt=""
                    className="h-full w-full object-contain transition-opacity duration-300"
                  />
                )
              ) : (
                <div className="grid h-full place-items-center px-6 text-center text-sm text-muted">
                  暂无动作图
                  <span className="mt-1 text-[11px]">后台补起始/结束图后这里会显示</span>
                </div>
              )}
              {canFlip ? (
                <span className="absolute bottom-2 right-2 rounded bg-ink/80 px-1.5 py-0.5 text-[10px] font-bold text-accent">
                  {frame === "start" ? "起始" : "结束"}
                </span>
              ) : null}
              {demoUrl ? (
                <span className="absolute bottom-2 right-2 rounded bg-ink/80 px-1.5 py-0.5 text-[10px] font-bold text-accent">
                  动图
                </span>
              ) : null}
            </div>
          </div>

          <div className="mt-4 px-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="font-display text-[26px] font-bold tracking-tight">{data.name_zh}</h1>
                {data.name_en ? <p className="mt-1 text-sm text-muted">{data.name_en}</p> : null}
              </div>
              {data.coach_core ? (
                <span className="shrink-0 rounded bg-ink px-1.5 py-0.5 text-[10px] font-extrabold text-accent">
                  主力
                </span>
              ) : null}
            </div>

            {tags.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-md border border-line bg-elevated px-2 py-1 text-[11px] font-bold text-muted"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}

            {risks.length > 0 ? (
              <p className="mt-2 text-[12px] text-muted">关节注意：{risks.join(" · ")}</p>
            ) : null}
          </div>

          <section className="mt-5 px-4">
            <h2 className="text-[13px] font-extrabold">动作要领</h2>
            {data.instructions_zh.length === 0 ? (
              <p className="mt-2 text-sm text-muted">暂无教案。</p>
            ) : (
              <ol className="mt-2 space-y-2">
                {data.instructions_zh.map((step, idx) => (
                  <li
                    key={idx}
                    className="flex gap-2.5 rounded-xl border border-line bg-elevated px-3 py-2.5"
                  >
                    <span className="font-num shrink-0 text-[12px] font-extrabold text-accent-text">
                      {idx + 1}
                    </span>
                    <p className="text-sm leading-relaxed">{step}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {data.cues_zh.length > 0 ? (
            <section className="mt-5 px-4">
              <h2 className="text-[13px] font-extrabold">发力提示</h2>
              <ul className="mt-2 space-y-1.5">
                {data.cues_zh.map((cue) => (
                  <li key={cue} className="text-sm text-ink">
                    · {cue}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {data.common_mistakes_zh.length > 0 ? (
            <section className="mt-5 px-4">
              <h2 className="text-[13px] font-extrabold">常见错误</h2>
              <ul className="mt-2 space-y-1.5">
                {data.common_mistakes_zh.map((item) => (
                  <li key={item} className="text-sm text-ink">
                    · {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {data.aliases.length > 0 ? (
            <section className="mt-5 px-4">
              <h2 className="text-[13px] font-extrabold">别名</h2>
              <p className="mt-2 text-sm text-muted">{data.aliases.join("、")}</p>
            </section>
          ) : null}

          <div className="fixed bottom-0 left-0 right-0 z-30 mx-auto max-w-md border-t border-line bg-bg/95 px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 backdrop-blur-sm">
            {addMsg ? (
              <p className="mb-2 text-center text-[12px] font-bold text-ok">
                {addMsg}{" "}
                <Link to="/" className="underline">
                  去今日
                </Link>
              </p>
            ) : null}
            {addErr ? <p className="mb-2 text-center text-[12px] font-bold text-danger">{addErr}</p> : null}
            <button
              type="button"
              disabled={adding}
              onClick={() => void addToToday()}
              className="pressable w-full rounded-xl bg-accent py-3 text-sm font-extrabold text-accent-ink disabled:opacity-60"
            >
              {adding ? "加入中…" : "加入今日训练"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
