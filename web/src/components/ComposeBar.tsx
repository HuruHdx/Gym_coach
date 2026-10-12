import { useState } from "react";
import { api } from "../lib/api";
import type { AgentReply } from "../types";

type Props = {
  onReply?: (reply: AgentReply) => void;
  placeholder?: string;
  autoFocus?: boolean;
};

export function ComposeBar({
  onReply,
  placeholder = "询问 AI 教练… 例如「今天练胸」",
  autoFocus,
}: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(raw?: string) {
    const t = (raw ?? text).trim();
    if (!t || busy) return;
    setBusy(true);
    try {
      const reply = await api<AgentReply>("/api/chat", {
        method: "POST",
        body: JSON.stringify({ text: t }),
      });
      sessionStorage.setItem("last_reply", JSON.stringify(reply));
      setText("");
      onReply?.(reply);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2 rounded-md border border-line bg-elevated py-1.5 pl-3 pr-1.5">
      <input
        className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
        placeholder={placeholder}
        value={text}
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && send()}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => send()}
        className="pressable rounded-sm bg-accent px-3 py-2 font-display text-xs font-bold text-accent-ink disabled:opacity-60"
      >
        {busy ? "…" : "发送"}
      </button>
    </div>
  );
}

export function useQuickSend() {
  const [busy, setBusy] = useState(false);
  async function send(t: string): Promise<AgentReply | null> {
    const text = t.trim();
    if (!text || busy) return null;
    setBusy(true);
    try {
      const reply = await api<AgentReply>("/api/chat", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      sessionStorage.setItem("last_reply", JSON.stringify(reply));
      return reply;
    } catch (e) {
      alert(String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }
  return { send, busy };
}
