import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toPng } from "html-to-image";
import { TrainingPoster, buildPosterModel } from "../components/TrainingPoster";
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

export function RecapPage() {
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
  const [saving, setSaving] = useState(false);
  const posterRef = useRef<HTMLDivElement>(null);
  const [editingTime, setEditingTime] = useState(false);
  const [minuteDraft, setMinuteDraft] = useState("");
  const current = local ?? session ?? null;
  const line = coachText(current?.summary);
  const streak = streakDays(history);
  const streakShown = Math.max(streak, current?.status === "done" ? 1 : 0);
  const poster = useMemo(
    () => (current ? buildPosterModel(current, history, streakShown, line) : null),
    [current, history, streakShown, line],
  );
  const minutes = current?.duration_minutes;

  async function savePoster() {
    const node = posterRef.current;
    if (!node || !current || saving) return;
    setSaving(true);
    try {
      const dataUrl = await toPng(node, { pixelRatio: 2, cacheBust: true });
      const link = document.createElement("a");
      link.download = `打卡海报-${current.session_date}.png`;
      link.href = dataUrl;
      link.click();
    } catch (error) {
      alert(String(error));
    } finally {
      setSaving(false);
    }
  }

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
    <div data-theme="dark" className="recap-poster relative flex min-h-full flex-col px-5 pb-8 pt-4 text-ink">
      {isLoading && <p className="mt-16 text-sm text-muted">正在打开结算…</p>}

      {!isLoading && !current && (
        <p className="mt-16 font-display text-display font-semibold">今天还没有完成的训练。</p>
      )}

      {current && poster && (
        <div className="mt-4 flex flex-1 flex-col">
          <TrainingPoster ref={posterRef} model={poster} />

          {!editingTime ? (
            <button
              type="button"
              onClick={() => {
                setMinuteDraft(minutes != null ? String(minutes) : "");
                setEditingTime(true);
              }}
              className="mt-3 w-full text-center text-xs font-semibold text-accent-text"
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
                className="w-20 rounded-md border border-line bg-elevated px-2 py-2 text-center font-display text-[16px] font-semibold text-ink"
              />
              <span className="text-xs text-muted">分钟</span>
              <button
                type="button"
                disabled={busy}
                onClick={() => void saveDuration()}
                className="rounded-full bg-accent px-3 py-2 text-xs font-semibold text-accent-ink disabled:opacity-50"
              >
                保存
              </button>
            </div>
          )}

          {showDetail && (
            <div className="mt-4 rounded-2xl border border-line bg-elevated p-4 rise-in">
              <p className="text-micro font-semibold tracking-[0.16em] text-accent-text">教练判断</p>
              <p className="mt-3 font-display text-title font-semibold leading-snug text-ink">
                {busy
                  ? "正在重写这场…"
                  : line || "这场的教练总结还没出来。可以点下面再生成一次。"}
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => void regenerate()}
                className="pressable mt-4 w-full rounded-full border border-line py-2.5 text-xs font-semibold text-muted disabled:opacity-50"
              >
                {busy ? "生成中…" : "重新生成总结"}
              </button>
            </div>
          )}

          <div className="mt-5 flex items-center gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => void savePoster()}
              className="pressable shrink-0 rounded-full border border-line px-4 py-3.5 text-xs font-semibold text-ink disabled:opacity-50"
            >
              {saving ? "生成中…" : "保存海报"}
            </button>
            <button
              type="button"
              onClick={() => setShowDetail((open) => !open)}
              className="pressable flex-1 rounded-full bg-accent py-3.5 font-display text-sm font-semibold text-accent-ink shadow-card"
            >
              {showDetail ? "收起详细总结" : "查看详细总结"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
