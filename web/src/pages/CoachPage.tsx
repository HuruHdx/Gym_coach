import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Apple,
  BarChart3,
  Dumbbell,
  LayoutGrid,
  PersonStanding,
  RefreshCw,
  Scale,
  StretchHorizontal,
  Zap,
} from "lucide-react";
import { api } from "../lib/api";
import { DraftCard } from "../components/DraftCard";
import { MessageFeedback } from "../components/MessageFeedback";
import type {
  AgentReply,
  Block,
  CardBlock,
  ConversationMessage,
  ConversationState,
  Profile,
  Suggestion,
  TrainingSession,
} from "../types";

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

type CoachAction = {
  id: string;
  title: string;
  sub: string;
  icon: ReactNode;
} & (
  | { kind: "prompt"; prompt: string }
  | { kind: "nav"; to: string }
  | { kind: "soon" }
);

const iconCls = "h-4 w-4";

function isDraftLocked(status: string | undefined) {
  return status === "confirmed" || status === "expired";
}

function createdAtMs(iso: string | null | undefined) {
  if (!iso) return Date.now();
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : Date.now();
}

function asSuggestions(raw: ConversationMessage["suggestions"]): Suggestion[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const items = raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const label = typeof item.label === "string" ? item.label.trim() : "";
    const prompt = typeof item.prompt === "string" ? item.prompt.trim() : "";
    if (!label && !prompt) return [];
    return [{ label: label || prompt, prompt: prompt || label }];
  });
  return items.length ? items : undefined;
}

function asCard(raw: ConversationMessage["card"]): CardBlock | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  return { ...raw, status: raw.status || "draft" };
}

function fromApiMessages(rows: ConversationMessage[]): ChatMessage[] {
  return rows.map((row) => {
    if (row.role === "user") {
      return {
        id: row.id,
        role: "user" as const,
        text: row.text,
        createdAt: createdAtMs(row.created_at),
      };
    }
    const card = asCard(row.card);
    const suggestions = asSuggestions(row.suggestions);
    return {
      id: row.id,
      role: "assistant" as const,
      text: row.text,
      card,
      suggestions,
      awaitingConfirm: Boolean(suggestions?.length) && !card,
      createdAt: createdAtMs(row.created_at),
    };
  });
}

const THINKING_STEPS = [
  "正在读取你的身体画像与伤痛记录...",
  "正在检索该部位动作库与历史最佳重量...",
  "正在规避伤痛动作，匹配个性化动作组合...",
  "正在生成专属组次、次数与负荷草稿...",
];

function buildActions(injuries: string[]): CoachAction[] {
  const knee = injuries.some((item) => item.includes("膝"));
  const lowerBack = injuries.some((item) => item.includes("腰"));
  const guards = [knee ? "膝盖" : "", lowerBack ? "腰" : ""].filter(Boolean);
  const legPrompt = guards.length ? `今天练腿，注意保护${guards.join("和")}` : "今天练腿";

  return [
    {
      id: "chest",
      title: "生成胸训",
      sub: "按画像排胸日草稿，可改再采纳",
      icon: <Dumbbell className={iconCls} strokeWidth={1.75} />,
      kind: "prompt",
      prompt: "今天练胸，安排40分钟",
    },
    {
      id: "back",
      title: "生成背训",
      sub: "强化背部宽度，带上次重量",
      icon: <StretchHorizontal className={iconCls} strokeWidth={1.75} />,
      kind: "prompt",
      prompt: "今天练背，想强化背部宽度",
    },
    {
      id: "legs",
      title: "练腿安排",
      sub: guards.length ? `已避开 ${guards.join("、")}` : "按恢复窗口排腿日",
      icon: <PersonStanding className={iconCls} strokeWidth={1.75} />,
      kind: "prompt",
      prompt: legPrompt,
    },
    {
      id: "full",
      title: "全身快练",
      sub: "约 30 分钟循环，赶时间也能练",
      icon: <Zap className={iconCls} strokeWidth={1.75} />,
      kind: "prompt",
      prompt: "随便来一套全身循环，30分钟",
    },
    {
      id: "weight",
      title: "记体重",
      sub: "跳到「我的」记一笔趋势",
      icon: <Scale className={iconCls} strokeWidth={1.75} />,
      kind: "nav",
      to: "/me",
    },
    {
      id: "food",
      title: "记饮食",
      sub: "即将上线",
      icon: <Apple className={iconCls} strokeWidth={1.75} />,
      kind: "soon",
    },
    {
      id: "analyze",
      title: "分析数据",
      sub: "即将上线",
      icon: <BarChart3 className={iconCls} strokeWidth={1.75} />,
      kind: "soon",
    },
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
  const { data: conversation, isLoading: conversationLoading } = useQuery({
    queryKey: ["chat-conversation"],
    queryFn: () => api<ConversationState>("/api/chat/conversation"),
  });
  const todayStatus: "none" | "active" | "done" = !todaySession
    ? "none"
    : todaySession.status === "done"
      ? "done"
      : todaySession.status === "active"
        ? "active"
        : "none";

  const actions = buildActions(profile.injuries || []);
  const primaryActions = actions.filter((item) => item.kind === "prompt");
  const secondaryActions = actions.filter((item) => item.kind !== "prompt");
  const promptChips = primaryActions;
  const [inputVal, setInputVal] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (!conversation || hydrated) return;
    setMessages(fromApiMessages(conversation.messages || []));
    setHydrated(true);
  }, [conversation, hydrated]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function flash(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), 1600);
  }

  async function handleSend(textToSend?: string) {
    const text = (textToSend ?? inputVal).trim();
    if (!text || busy) return;

    const userMsgId = `user-${Date.now()}`;
    const thinkingId = `thinking-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", text, createdAt: Date.now() },
      { id: thinkingId, role: "thinking", step: THINKING_STEPS[0], elapsedSec: 0 },
    ]);
    setInputVal("");
    setBusy(true);

    const startTime = Date.now();
    let stepIdx = 0;

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

      const totalElapsed = Math.max(1, Math.round((Date.now() - startTime) / 1000));
      const textBlock = reply.blocks.find(
        (b): b is Extract<Block, { kind: "text" }> => b.kind === "text",
      );
      const cardBlock = reply.blocks.find((b): b is CardBlock => b.kind === "card");

      clearInterval(timer);

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
      void qc.invalidateQueries({ queryKey: ["chat-conversation"] });
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
    void qc.invalidateQueries({ queryKey: ["training-today"] });
    void qc.invalidateQueries({ queryKey: ["training-sessions"] });
    void qc.invalidateQueries({ queryKey: ["training-dashboard"] });
    void qc.invalidateQueries({ queryKey: ["exercises"] });
    navigate("/");
  }

  async function startNewChat() {
    if (busy) return;
    try {
      const next = await api<ConversationState>("/api/chat/conversation", {
        method: "POST",
      });
      setMessages(fromApiMessages(next.messages || []));
      setHydrated(true);
      void qc.setQueryData(["chat-conversation"], next);
    } catch (e) {
      alert(`无法开始新对话：${String(e)}`);
    }
  }

  function runAction(action: CoachAction) {
    if (busy) return;
    if (action.kind === "prompt") {
      void handleSend(action.prompt);
      return;
    }
    if (action.kind === "nav") {
      navigate(action.to);
      return;
    }
    flash("即将上线");
  }

  const showThread = hydrated && messages.length > 0;
  const showWelcome = hydrated && messages.length === 0 && !conversationLoading;

  const bottomChips = showWelcome ? actions : promptChips;

  return (
    <div className="flex h-full min-h-0 flex-col px-page pb-2 pt-3">
      <header className="flex shrink-0 items-center justify-between pb-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-tint text-accent-text">
            <LayoutGrid className="h-3.5 w-3.5" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h1 className="font-display text-title font-semibold tracking-tight">AI 教练</h1>
            <p className="mt-0.5 truncate text-micro text-muted">
              {profile.goal} · {profile.experience} · 每周 {profile.days_per_week} 练
            </p>
          </div>
        </div>
        <button
          type="button"
          disabled={busy || (!showThread && !conversationLoading)}
          onClick={() => void startNewChat()}
          aria-label="新对话"
          title="新对话"
          className="pressable grid h-9 w-9 shrink-0 place-items-center rounded-md border border-line bg-elevated text-ink disabled:opacity-40"
        >
          <RefreshCw className="h-4 w-4" strokeWidth={1.75} />
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain py-3">
          {conversationLoading && !hydrated && (
            <p className="text-center text-meta text-muted">加载对话…</p>
          )}

          {showWelcome && (
            <div className="rise-in">
              <div className="px-3 py-2 text-center">
                <p className="font-display text-title font-semibold leading-snug text-accent-text">
                  Hi，我是你的训练教练，请问有什么可以帮到你？
                </p>
                <p className="mt-2 text-micro leading-relaxed text-muted">
                  点入口或直接说想练什么，会落成可改草稿。
                </p>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2">
                {primaryActions.map((action) => (
                  <button
                    key={action.id}
                    type="button"
                    disabled={busy}
                    onClick={() => runAction(action)}
                    className="pressable rounded-lg border border-line bg-elevated px-3 py-3 text-left shadow-card"
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-md bg-tint text-accent-text">
                      {action.icon}
                    </span>
                    <span className="mt-2 block text-meta font-semibold text-ink">{action.title}</span>
                    <span className="mt-0.5 block truncate text-micro text-muted">{action.sub}</span>
                  </button>
                ))}
              </div>

              <div className="mt-2 grid grid-cols-3 gap-1.5">
                {secondaryActions.map((action) => (
                  <button
                    key={action.id}
                    type="button"
                    disabled={busy}
                    onClick={() => runAction(action)}
                    className={`pressable rounded-md border border-line bg-elevated px-2 py-2 text-center ${
                      action.kind === "soon" ? "opacity-50" : ""
                    }`}
                  >
                    <span className="mx-auto grid h-7 w-7 place-items-center text-accent-text">
                      {action.icon}
                    </span>
                    <span className="mt-1 block text-micro font-semibold text-ink">{action.title}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => {
            if (m.role === "user") {
              return (
                <div key={m.id} className="flex justify-end rise-in">
                  <div className="max-w-[85%] rounded-lg rounded-tr-sm bg-ink px-4 py-2.5 text-meta font-medium text-accent-ink shadow-card">
                    {m.text}
                  </div>
                </div>
              );
            }

            if (m.role === "thinking") {
              return (
                <div key={m.id} className="flex gap-2.5 rise-in">
                  <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-tint text-micro font-semibold text-accent-text">
                    AI
                  </div>
                  <div className="min-w-0 flex-1 rounded-lg rounded-tl-sm border border-line bg-elevated p-3 shadow-card">
                    <div className="flex items-center gap-2">
                      <span className="grid h-2 w-2 rounded-full bg-accent opacity-80" />
                      <span className="text-meta font-semibold text-ink">教练正在编排…</span>
                      <span className="text-micro text-muted">({m.elapsedSec}s)</span>
                    </div>
                    <p className="mt-1 text-meta text-muted">{m.step}</p>
                  </div>
                </div>
              );
            }

            if (m.role === "assistant") {
              return (
                <div key={m.id} className="flex flex-col gap-2 rise-in">
                  <div className="flex gap-2.5">
                    <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ink text-micro font-semibold text-accent-ink">
                      AI
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="rounded-lg rounded-tl-sm border border-line bg-elevated p-3.5 shadow-card">
                        {m.elapsedSec != null && (
                          <div className="mb-1 text-micro font-medium text-muted">
                            {m.card
                              ? `已按画像排好 · ${m.elapsedSec}s`
                              : m.awaitingConfirm
                                ? `先跟你确认 · ${m.elapsedSec}s`
                                : `${m.elapsedSec}s`}
                          </div>
                        )}
                        <p className="text-meta leading-relaxed text-ink">{m.text}</p>
                      </div>

                      {m.traceId != null && <MessageFeedback traceId={m.traceId} />}

                      {m.suggestions && m.suggestions.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {m.suggestions.map((s) => (
                            <button
                              key={s.prompt}
                              type="button"
                              disabled={busy}
                              className="pressable rounded-full border border-line bg-bg px-2.5 py-1 text-micro font-semibold text-ink"
                              onClick={() => void handleSend(s.prompt)}
                            >
                              {s.label}
                            </button>
                          ))}
                        </div>
                      )}

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
                          <span className="text-micro text-muted">调试轨迹 #{m.traceId}</span>
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

        <div className="shrink-0 border-t border-line bg-bg pt-2">
          <div className="no-scrollbar mb-2 flex gap-1.5 overflow-x-auto py-0.5">
            {bottomChips.map((item) => (
              <button
                key={`chip-${item.id}`}
                type="button"
                disabled={busy}
                onClick={() => runAction(item)}
                className={`pressable flex shrink-0 items-center gap-1.5 rounded-full border border-line bg-elevated px-2.5 py-1.5 text-micro font-semibold text-ink ${
                  item.kind === "soon" ? "opacity-50" : ""
                }`}
              >
                <span className="text-accent-text">{item.icon}</span>
                {item.title}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-line bg-elevated px-3 py-1.5 shadow-card">
            <input
              className="min-w-0 flex-1 bg-transparent text-[16px] outline-none placeholder:text-muted"
              placeholder={busy ? "教练正在生成中…" : "询问 AI 教练，如「练背」"}
              value={inputVal}
              disabled={busy}
              onChange={(e) => setInputVal(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void handleSend()}
            />
            <button
              type="button"
              disabled={busy || !inputVal.trim()}
              onClick={() => void handleSend()}
              className="pressable rounded-md bg-accent px-3 py-2 font-display text-label font-semibold text-accent-ink disabled:opacity-40"
            >
              {busy ? "…" : "发送"}
            </button>
          </div>
          <p className="mt-1 text-center text-micro text-muted">内容由 AI 生成 · 采纳前可改草稿</p>
        </div>
      </div>

      {toast && (
        <p className="pointer-events-none fixed bottom-24 left-1/2 z-30 -translate-x-1/2 rounded-full bg-ink px-3 py-1.5 text-micro font-semibold text-accent-ink">
          {toast}
        </p>
      )}
    </div>
  );
}
