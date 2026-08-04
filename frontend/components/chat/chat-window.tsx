"use client";

import { useRef, useState, useEffect } from "react";
import { PanelRight, Send, Sparkles, Square } from "lucide-react";
import { useConsultStream, type ConsultEvent } from "@/hooks/use-consult-stream";
import { useAuthStore } from "@/lib/auth-store";
import { cn } from "@/lib/cn";
import type { ChatHistoryItem } from "@/lib/types";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

function processNote(event: ConsultEvent): string | null {
  if (event.event === "started") return "已受理您的问题，正在分析…";
  if (event.event === "evidence") return `已检索 ${String(event.data.count ?? 0)} 条相关资料`;
  if (event.event === "completed") return "回复已生成";
  if (event.event === "error") return String(event.data.message ?? "处理出错");
  return null;
}

const ACTION_LABELS: Record<string, string> = {
  request_refund: "已发起退款申请",
  create_ticket: "已创建工单",
  list_payments: "已查询支付记录",
};

export function ChatWindow() {
  const identity = useAuthStore((state) => state.identity);
  const { events, running, finalResponse, streamText, error, run, cancel } = useConsultStream();
  const [input, setInput] = useState("");
  const [showContext, setShowContext] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Persist the conversation per identity so history survives navigating to
  // another console and back (and page refreshes).
  const storageKey = identity
    ? `clouddesk-chat-${identity.tenantId}:${identity.userId}`
    : null;

  useEffect(() => {
    if (!storageKey) return;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        const saved = JSON.parse(raw) as { threadId?: string | null; messages?: ChatMessage[] };
        setThreadId(saved.threadId ?? null);
        setMessages(Array.isArray(saved.messages) ? saved.messages : []);
      }
    } catch {
      /* ignore malformed saved state */
    }
  }, [storageKey]);

  useEffect(() => {
    if (!storageKey) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ threadId, messages }));
    } catch {
      /* ignore quota errors */
    }
  }, [storageKey, threadId, messages]);

  // SSE process events (evidence / processing notes) shown under the current turn.
  const processSteps = events.filter((event) => event.event !== "done");
  const evidenceRaw = events.find((e) => e.event === "evidence")?.data.count;
  const evidenceCount = typeof evidenceRaw === "number" ? evidenceRaw : 0;
  const evidenceResults = events.find((e) => e.event === "evidence")?.data.results as
    | Array<{ title: string; snippet?: string; score?: number | null; source?: string | null }>
    | undefined;

  // Append the assistant reply once a turn completes (multi-turn history).
  useEffect(() => {
    if (finalResponse) {
      setMessages((prev) => [...prev, { role: "assistant", content: finalResponse }]);
    }
  }, [finalResponse]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, processSteps.length, running]);

  const submit = () => {
    const message = input.trim();
    if (!message || running) return;
    const thread = threadId ?? `chat-${crypto.randomUUID().slice(0, 8)}`;
    setThreadId(thread);
    const history: ChatHistoryItem[] = messages.map((msg) => ({
      role: msg.role,
      content: msg.content,
    }));
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    void run({ thread_id: thread, message, history });
  };

  return (
    <div className="flex h-full min-h-0">
      {/* Main conversation column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-6">
          <div>
            <p className="text-sm font-medium">智能客服对话</p>
            <p className="text-xs text-muted-foreground">
              {messages.length > 0 ? `${messages.length} 条消息 · ${threadId ? "多轮对话中" : "新对话"}` : "新对话"}
            </p>
          </div>
          <button
            onClick={() => setShowContext((v) => !v)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs transition-colors",
              showContext
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <PanelRight className="h-3.5 w-3.5" />
            上下文
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-2xl px-6 py-8">
            {messages.length === 0 && !running && !error && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/10">
                  <Sparkles className="h-6 w-6 text-accent" />
                </div>
                <h2 className="text-lg font-medium text-foreground">CloudDesk 智能客服</h2>
                <p className="mt-1 max-w-md text-sm leading-relaxed text-muted-foreground">
                  我可以协助处理账户、账单、产品技术支持、SLA 与工单相关问题。
                  描述您遇到的问题即可开始，支持连续对话。
                </p>
              </div>
            )}

            {/* Full message history (multi-turn) */}
            {messages.map((message, index) =>
              message.role === "user" ? (
                <div key={index} className="mb-4 flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-md bg-accent px-4 py-2.5 text-sm leading-relaxed text-accent-foreground">
                    {message.content}
                  </div>
                </div>
              ) : (
                <div key={index} className="mb-4 flex items-start gap-2.5">
                  <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted">
                    <Sparkles className="h-3 w-3 text-muted-foreground" />
                  </span>
                  <div className="min-w-0 rounded-2xl rounded-tl-md border border-border bg-card px-4 py-3">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                      {message.content}
                    </p>
                  </div>
                </div>
              ),
            )}

            {/* Live processing trail for the in-flight turn */}
            {processSteps.length > 0 && !finalResponse && (
              <div className="mb-4">
                {processSteps.map((event, index) =>
                  event.event === "action" ? (
                    <div
                      key={index}
                      className="mb-3 rounded-xl border border-accent/40 bg-accent/5 px-4 py-3"
                    >
                      <p className="text-sm font-medium text-accent">
                        {ACTION_LABELS[String(event.data.action)] ?? "已执行业务操作"}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-foreground">
                        {String(event.data.summary ?? "")}
                      </p>
                    </div>
                  ) : (
                    <div key={index} className="mb-3 flex items-start gap-2.5">
                      <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted">
                        <Sparkles className="h-3 w-3 text-muted-foreground" />
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">
                          {event.event === "evidence" ? "正在检索企业知识库" : "正在处理"}
                        </p>
                        <p className="text-xs text-muted-foreground">{processNote(event)}</p>
                        {event.event === "evidence" && (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {Array.from({ length: Number(event.data.count ?? 0) }).map((_, i) => (
                              <span
                                key={i}
                                className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground"
                              >
                                资料 {i + 1}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ),
                )}
              </div>
            )}

            {/* Live streaming answer bubble */}
            {running && streamText && (
              <div className="mb-4 flex items-start gap-2.5">
                <span className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted">
                  <Sparkles className="h-3 w-3 text-muted-foreground" />
                </span>
                <div className="min-w-0 rounded-2xl rounded-tl-md border border-border bg-card px-4 py-3">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                    {streamText}
                  </p>
                </div>
              </div>
            )}

            {running && !finalResponse && !streamText && (
              <div className="mb-4 flex items-center gap-2 text-xs text-muted-foreground">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                正在处理
              </div>
            )}

            {error && (
              <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                {error}
              </div>
            )}
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-border px-6 py-4">
          <div className="mx-auto max-w-2xl">
            <div className="flex items-end gap-2 rounded-2xl border border-border bg-card px-3 py-2 focus-within:ring-2 focus-within:ring-ring">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
                rows={1}
                placeholder="描述您的问题，支持连续对话…"
                className="max-h-40 min-h-6 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm leading-relaxed outline-none placeholder:text-muted-foreground"
              />
              {running ? (
                <button
                  onClick={cancel}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-muted"
                  aria-label="停止"
                >
                  <Square className="h-4 w-4" />
                </button>
              ) : (
                <button
                  onClick={submit}
                  disabled={!input.trim()}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
                  aria-label="发送"
                >
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
            <p className="mt-2 px-1 text-xs text-muted-foreground">
              可协助处理账户、账单、技术支持、SLA 与工单问题 · 支持多轮上下文
            </p>
          </div>
        </div>
      </div>

      {/* Context drawer */}
      {showContext && (
        <aside className="w-80 shrink-0 border-l border-border bg-card/40">
          <div className="space-y-5 p-5">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                当前对话
              </h3>
              <p className="mt-1.5 text-sm">{messages.length} 条消息</p>
              <p className="text-xs text-muted-foreground">线索 ID：{threadId ?? "-"}</p>
            </div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                检索证据
              </h3>
              {evidenceResults && evidenceResults.length > 0 ? (
                <ul className="mt-2 space-y-2">
                  {evidenceResults.map((result, index) => (
                    <li key={index} className="rounded-md border border-border bg-background p-2.5">
                      <p className="text-sm font-medium leading-snug">{result.title}</p>
                      {result.snippet && (
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                          {result.snippet}
                        </p>
                      )}
                      {typeof result.score === "number" && (
                        <p className="mt-1 text-[11px] tabular-nums text-muted-foreground">
                          相关度 {result.score.toFixed(3)}
                          {result.source ? ` · ${result.source}` : ""}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1.5 text-sm text-muted-foreground">
                  {evidenceCount > 0 ? `${evidenceCount} 条相关知识` : "暂未检索到相关知识"}
                </p>
              )}
            </div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                当前身份
              </h3>
              <div className="mt-1.5 flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-[11px] font-medium text-accent-foreground">
                  {identity?.userName.slice(0, 1) ?? "?"}
                </span>
                <div className="leading-tight">
                  <p className="text-sm">{identity?.userName}</p>
                  <p className="text-xs text-muted-foreground">{identity?.tenantSlug}</p>
                </div>
              </div>
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}
