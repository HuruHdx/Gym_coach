import { useState } from "react";
import { api } from "../lib/api";

const DOWN_TAGS: { id: string; label: string }[] = [
  { id: "wrong_topic", label: "分流错" },
  { id: "wrong_route", label: "路由错" },
  { id: "bad_answer", label: "回答差" },
  { id: "bad_plan", label: "课表差" },
  { id: "tone", label: "语气怪" },
  { id: "other", label: "其他" },
];

type Props = {
  traceId: number;
};

export function MessageFeedback({ traceId }: Props) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [openDown, setOpenDown] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function send(next: "up" | "down", nextTags: string[], nextNote: string) {
    setBusy(true);
    setError("");
    try {
      await api("/api/feedback", {
        method: "POST",
        body: JSON.stringify({
          rating: next,
          tags: next === "down" ? nextTags : [],
          note: next === "down" ? nextNote : "",
          trace_id: traceId,
        }),
      });
      setRating(next);
      setSaved(true);
      if (next === "up") {
        setOpenDown(false);
        setTags([]);
        setNote("");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  function onUp() {
    void send("up", [], "");
  }

  function onDownClick() {
    setOpenDown(true);
    setSaved(false);
  }

  function toggleTag(id: string) {
    setTags((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));
  }

  function onSubmitDown() {
    if (!tags.length) {
      setError("至少选一个原因");
      return;
    }
    void send("down", tags, note.trim());
  }

  return (
    <div className="mt-1.5">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy}
          aria-label="有用"
          onClick={onUp}
          className={`pressable rounded-md px-1.5 py-0.5 text-[11px] ${
            rating === "up" ? "bg-ink text-bg" : "text-muted hover:bg-bg hover:text-ink"
          }`}
        >
          👍
        </button>
        <button
          type="button"
          disabled={busy}
          aria-label="不好"
          onClick={onDownClick}
          className={`pressable rounded-md px-1.5 py-0.5 text-[11px] ${
            rating === "down" ? "bg-ink text-bg" : "text-muted hover:bg-bg hover:text-ink"
          }`}
        >
          👎
        </button>
        {saved && rating === "up" && (
          <span className="text-[10px] text-muted">已记录</span>
        )}
        {saved && rating === "down" && (
          <span className="text-[10px] text-muted">已记下，待导出评测</span>
        )}
      </div>

      {openDown && (
        <div className="mt-1.5 space-y-1.5 rounded-lg border border-line bg-bg p-2">
          <div className="flex flex-wrap gap-1">
            {DOWN_TAGS.map((tag) => {
              const on = tags.includes(tag.id);
              return (
                <button
                  key={tag.id}
                  type="button"
                  disabled={busy}
                  onClick={() => toggleTag(tag.id)}
                  className={`pressable rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    on
                      ? "border border-ink bg-ink text-bg"
                      : "border border-line text-muted hover:border-ink hover:text-ink"
                  }`}
                >
                  {tag.label}
                </button>
              );
            })}
          </div>
          <input
            className="w-full rounded-md border border-line bg-elevated px-2 py-1 text-[11px] outline-none placeholder:text-muted focus:border-ink"
            placeholder="可选：一句话说明哪里不对"
            value={note}
            disabled={busy}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSubmitDown()}
          />
          <div className="flex items-center justify-between gap-2">
            {error ? <span className="text-[10px] text-red-600">{error}</span> : <span />}
            <button
              type="button"
              disabled={busy || !tags.length}
              onClick={onSubmitDown}
              className="pressable rounded-md bg-accent px-2.5 py-1 text-[10px] font-extrabold text-accent-ink disabled:opacity-40"
            >
              提交
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
