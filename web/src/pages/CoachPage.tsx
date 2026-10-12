import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { DraftCard } from "../components/DraftCard";
import type { AgentReply, Block, CardBlock, Profile, Suggestion, TrainingSession } from "../types";

type ChatMessage =
  | {
      id: string;
      role: "user";
      text: string;
      createdAt?: number;
    }
  | {
      id: string;
      role: "thinking";
      step: string;
      elapsedSec: number;
    }
  | {
      id: string;
      role: "assistant";
      text: string;
      elapsedSec?: number;
      card?: CardBlock;
      suggestions?: Suggestion[];
      awaitingConfirm?: boolean;
      traceId?: number | null;
      createdAt?: number;
    };

function startOfLocalDay(ts = Date.now()) {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function isDraftLocked(status: string | undefined) {
  return status === "confirmed" || status === "expired";
}

/** 跨自然日的未采纳草稿失效，避免昨天计划今天还能再点采纳 */
function sanitizeChatHistory(messages: ChatMessage[]): ChatMessage[] {
  const today0 = startOfLocalDay();
  return messages.map((m) => {
    if (m.role !== "assistant" || !m.card || m.card.card_type !== "training_draft") {
      return m;
    }
    if (isDraftLocked(m.card.status)) return m;
    const created = m.createdAt ?? 0;
    // 无时间戳的旧缓存、或非今天生成的草稿 → 失效
    if (!created || created < today0) {
      return {
        ...m,
        card: {
          ...m.card,
          status: "expired",
          actions: [],
          meta: { ...m.card.meta, expired_reason: "stale_day" },
        },
      };
    }
    return m;
  });
}

const THINKING_STEPS = [
  "正在读取你的身体画像与伤痛记录...",
  "正在检索该部位动作库与历史最佳重量...",
  "正在规避伤痛动作，匹配个性化动作组合...",
  "正在生成专属组次、次数与负荷草稿...",
];

const CHAT_STORAGE_KEY = "gym_coach_chat_history";

function quickPrompts(injuries: string[]) {
  const knee = injuries.some((item) => item.includes("膝"));
  const lowerBack = injuries.some((item) => item.includes("腰"));
  const guards = [knee ? "膝盖" : "", lowerBack ? "腰" : ""].filter(Boolean);
  const legPrompt = guards.length ? `今天练腿，注意保护${guards.join("和")}` : "今天练腿";
  return [
    { label: "定制胸训", prompt: "今天练胸，安排40分钟", icon: "⚡" },
    { label: "定制背训", prompt: "今天练背，想强化背部宽度", icon: "🎯" },
    { label: "练腿安排", prompt: legPrompt, icon: "🦵" },
    { label: "全身快练", prompt: "随便来一套全身循环，30分钟", icon: "⏱️" },
  ];
}

type Props = { profile: Profile };

export function CoachPage({ profile }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const scrollRef = useRef<HTMLDivElement>(null);
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

  const prompts = quickPrompts(profile.injuries || []);
  const [inputVal, setInputVal] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const saved = localStorage.getItem(CHAT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as ChatMessage[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          return sanitizeChatHistory(parsed);
        }
      }
    } catch {
      // ignore
    }
    // 恢复上一次的草稿（仅限当天未过期）
    const raw = sessionStorage.getItem("last_reply");
    if (!raw) return [];
    try {
      const reply = JSON.parse(raw) as AgentReply;
      const textBlock = reply.blocks.find(
        (b): b is Extract<Block, { kind: "text" }> => b.kind === "text",
      );
      const cardBlock = reply.blocks.find(
        (b): b is CardBlock => b.kind === "card",
      );
      return sanitizeChatHistory([
        {
          id: "init-assistant",
          role: "assistant",
          text: textBlock?.text || "这是为你生成的建议：",
          card: cardBlock,
          suggestions: reply.suggestions,
          awaitingConfirm: Boolean(reply.suggestions?.length) && !cardBlock,
          traceId: reply.trace_id,
          createdAt: Date.now(),
        },
      ]);
    } catch {
      return [];
    }
  });

  useEffect(() => {
    // 剔除正在思考的气泡，持久化存储最近 50 条消息
    const persistent = messages.filter((m) => m.role !== "thinking").slice(-50);
    if (persistent.length > 0) {
      try {
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(persistent));
      } catch {
        // ignore
      }
    }
  }, [messages]);

  // 自动滚动到底部
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function handleSend(textToSend?: string) {
    const text = (textToSend ?? inputVal).trim();
    if (!text || busy) return;

    const userMsgId = `user-${Date.now()}`;
    const thinkingId = `thinking-${Date.now()}`;

    // 1. 立即上屏用户气泡 & 思考气泡
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", text, createdAt: Date.now() },
      { id: thinkingId, role: "thinking", step: THINKING_STEPS[0], elapsedSec: 0 },
    ]);
    setInputVal("");
    setBusy(true);

    const startTime = Date.now();
    let stepIdx = 0;

    // 思考动态计时器
    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      stepIdx = (stepIdx + 1) % THINKING_STEPS.length;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingId && m.role === "thinking"
            ? { ...m, step: THINKING_STEPS[stepIdx], elapsedSec: elapsed }
            : m,
        ),
      );
    }, 1200);

    try {
      const latestDraft = [...messages]
        .reverse()
        .find(
          (m): m is Extract<ChatMessage, { role: "assistant" }> =>
            m.role === "assistant" &&
            Boolean(m.card?.items?.length) &&
            !isDraftLocked(m.card?.status),
        );
      const reply = await api<AgentReply>("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          text,
          draft_title: latestDraft?.card?.title ?? null,
          draft_items:
            latestDraft?.card?.items.map((it) => ({
              title: it.title,
              selected: it.selected,
              meta: it.meta,
            })) ?? [],
        }),
      });
      sessionStorage.setItem("last_reply", JSON.stringify(reply));

      const totalElapsed = Math.max(1, Math.round((Date.now() - startTime) / 1000));
      const textBlock = reply.blocks.find(
        (b): b is Extract<Block, { kind: "text" }> => b.kind === "text",
      );
      const cardBlock = reply.blocks.find(
        (b): b is CardBlock => b.kind === "card",
      );

      clearInterval(timer);

      // 2. 将思考气泡替换为正式 AI 回复气泡
      setMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingId
            ? {
                id: `ai-${Date.now()}`,
                role: "assistant",
                text: textBlock?.text || "训练计划已为你定制生成。",
                card: cardBlock
                  ? { ...cardBlock, status: cardBlock.status || "draft" }
                  : undefined,
                suggestions: reply.suggestions,
                awaitingConfirm: Boolean(reply.suggestions?.length) && !cardBlock,
                elapsedSec: totalElapsed,
                traceId: reply.trace_id,
                createdAt: Date.now(),
              }
            : m,
        ),
      );
    } catch (e) {
      clearInterval(timer);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === thinkingId
            ? {
                id: `err-${Date.now()}`,
                role: "assistant",
                text: `抱歉，定制失败：${String(e)}`,
              }
            : m,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  function handleCardChange(msgId: string, updatedCard: CardBlock) {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId && m.role === "assistant" ? { ...m, card: updatedCard } : m,
      ),
    );
  }

  function handleAdopted(_session: TrainingSession, confirmedCard: CardBlock, msgId: string) {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId && m.role === "assistant" ? { ...m, card: confirmedCard } : m,
      ),
    );
    sessionStorage.removeItem("last_reply");
    void qc.invalidateQueries({ queryKey: ["training-today"] });
    void qc.invalidateQueries({ queryKey: ["training-sessions"] });
    void qc.invalidateQueries({ queryKey: ["training-dashboard"] });
    void qc.invalidateQueries({ queryKey: ["exercises"] });
    navigate("/");
  }

  function clearHistory() {
    setMessages([]);
    localStorage.removeItem(CHAT_STORAGE_KEY);
    sessionStorage.removeItem("last_reply");
  }

  return (
    <div className="flex min-h-full flex-col px-4 pb-3 pt-3">
      {/* 顶部标题区 */}
      <div className="flex items-center justify-between border-b border-line pb-2.5">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="grid h-2.5 w-2.5 rounded-full bg-accent animate-pulse" />
            <h1 className="font-display text-xl font-bold tracking-tight">AI 专属教练</h1>
          </div>
          <p className="mt-0.5 text-[11px] text-muted">
            {profile.goal} · {profile.experience} · {profile.weight_kg}kg
            {profile.session_minutes ? ` · ${profile.session_minutes}分` : ""}
            {profile.preferences?.length && profile.preferences.length < 4
              ? ` · ${profile.preferences.join("/")}`
              : ""}
            {profile.injuries.length > 0
              ? ` · 伤痛规避(${profile.injuries.join("、")})`
              : " · 无伤痛记录"}
          </p>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={clearHistory}
            className="pressable rounded-md border border-line bg-elevated px-2 py-1 text-[11px] font-bold text-muted hover:text-ink"
          >
            清空对话
          </button>
        )}
      </div>

      {/* 对话流区 */}
      <div className="flex-1 space-y-4 py-4">
        {/* 空对话时的欢迎卡片 */}
        {messages.length === 0 && (
          <div className="relative overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-[var(--hero-a)] via-bg to-bg p-5 rise-in">
            <div className="flex items-center gap-2">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-ink font-display text-xs font-black text-accent">
                AI
              </div>
              <span className="font-display text-base font-bold">Hi，我是你的私教</span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              告诉我你今天想练什么，我按你的目标和记录来排。生成草稿后可自由换动作、微调重量，再一键采纳执行。
            </p>

            <div className="mt-4 grid grid-cols-2 gap-2">
              {prompts.map((q) => (
                <button
                  key={q.label}
                  type="button"
                  disabled={busy}
                  className="pressable flex flex-col justify-between rounded-xl border border-line bg-elevated p-3 text-left shadow-sm hover:border-ink/40"
                  onClick={() => handleSend(q.prompt)}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm">{q.icon}</span>
                    <span className="font-display text-xs font-bold text-ink">{q.label}</span>
                  </div>
                  <span className="mt-1 line-clamp-1 text-[10px] text-muted">{q.prompt}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 消息列表 */}
        {messages.map((m) => {
          if (m.role === "user") {
            return (
              <div key={m.id} className="flex justify-end rise-in">
                <div className="max-w-[85%] rounded-2xl rounded-tr-none bg-ink px-4 py-2.5 text-xs font-medium text-bg shadow-sm">
                  {m.text}
                </div>
              </div>
            );
          }

          if (m.role === "thinking") {
            return (
              <div key={m.id} className="flex gap-2.5 rise-in">
                <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent/20 font-display text-[10px] font-black text-accent-ink">
                  AI
                </div>
                <div className="min-w-0 flex-1 rounded-2xl rounded-tl-none border border-line bg-elevated p-3 shadow-sm">
                  <div className="flex items-center gap-2">
                    <span className="grid h-2 w-2 rounded-full bg-accent animate-ping" />
                    <span className="font-display text-xs font-bold text-ink">
                      教练正在思考与编排...
                    </span>
                    <span className="text-[10px] text-muted">({m.elapsedSec}s)</span>
                  </div>
                  <p className="mt-1 text-xs text-muted transition-all duration-300">
                    {m.step}
                  </p>
                </div>
              </div>
            );
          }

          if (m.role === "assistant") {
            return (
              <div key={m.id} className="flex flex-col gap-2 rise-in">
                <div className="flex gap-2.5">
                  <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ink font-display text-[10px] font-black text-accent">
                    AI
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="rounded-2xl rounded-tl-none border border-line bg-elevated p-3.5 shadow-sm">
                      {m.elapsedSec != null && (
                        <div className="mb-1 text-[10px] font-semibold text-muted">
                          {m.awaitingConfirm
                            ? `先跟你确认 · 用时 ${m.elapsedSec} 秒`
                            : `已根据画像完成规划 · 用时 ${m.elapsedSec} 秒`}
                        </div>
                      )}
                      <p className="text-xs leading-relaxed text-ink">{m.text}</p>
                    </div>

                    {m.suggestions && m.suggestions.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {m.suggestions.map((s) => (
                          <button
                            key={s.prompt}
                            type="button"
                            disabled={busy}
                            className="pressable rounded-full border border-line bg-bg px-2.5 py-1 text-[11px] font-bold text-ink hover:border-ink"
                            onClick={() => handleSend(s.prompt)}
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* 内嵌的交互式可定制草稿卡 */}
                    {m.card && m.card.card_type === "training_draft" && (
                      <div className="mt-2.5">
                        <DraftCard
                          card={m.card}
                          todayStatus={todayStatus}
                          onChange={(newCard) => handleCardChange(m.id, newCard)}
                          onAdopted={(session, confirmedCard) =>
                            handleAdopted(session, confirmedCard, m.id)
                          }
                        />
                      </div>
                    )}

                    {m.traceId != null && (
                      <div className="mt-1.5 text-right">
                        <span className="text-[10px] text-muted">调试轨迹 #{m.traceId}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          }

          return null;
        })}

        <div ref={scrollRef} />
      </div>

      {/* 底部快捷胶囊（有对话记录时依然快捷可点） */}
      {messages.length > 0 && !busy && (
        <div className="no-scrollbar mb-2 flex gap-1.5 overflow-x-auto py-1">
          {prompts.map((q) => (
            <button
              key={q.label}
              type="button"
              className="pressable shrink-0 rounded-full border border-line bg-elevated px-2.5 py-1 text-[11px] font-bold text-muted hover:border-ink hover:text-ink"
              onClick={() => handleSend(q.prompt)}
            >
              {q.icon} {q.label}
            </button>
          ))}
        </div>
      )}

      {/* 底部发送输入栏 */}
      <div className="sticky bottom-0 z-20 shrink-0 border-t border-line bg-bg/95 pt-2 backdrop-blur-sm">
        <div className="flex items-center gap-2 rounded-xl border border-line bg-elevated px-3 py-1.5 shadow-sm focus-within:border-ink">
          <input
            className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted"
            placeholder={busy ? "教练正在生成中..." : "告诉教练你想练什么，如「练背」..."}
            value={inputVal}
            disabled={busy}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
          />
          <button
            type="button"
            disabled={busy || !inputVal.trim()}
            onClick={() => handleSend()}
            className="pressable rounded-lg bg-accent px-3 py-1.5 font-display text-xs font-extrabold text-accent-ink disabled:opacity-40"
          >
            {busy ? "…" : "发送"}
          </button>
        </div>
        <p className="mt-1 text-center text-[10px] text-muted">
          内容由 AI 模型生成 · 采纳前可随意调整
        </p>
      </div>
    </div>
  );
}
