"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { useConsultStream, type ConsultEvent } from "@/hooks/use-consult-stream";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/form";
import { InlineLoader } from "@/components/ui/states";
import { cn } from "@/lib/cn";

const EVENT_LABELS: Record<string, string> = {
  started: "已受理",
  evidence: "检索证据",
  completed: "处理完成",
  done: "完成",
  error: "错误",
};

function eventDescription(event: ConsultEvent): string {
  if (event.event === "started") return "已接收您的问题，正在处理。";
  if (event.event === "evidence") return `已检索到 ${String(event.data.count ?? 0)} 条相关资料。`;
  if (event.event === "completed") return "回复已生成。";
  if (event.event === "done") return "处理流程结束。";
  if (event.event === "error") return String(event.data.message ?? "处理出错");
  return "";
}

export default function ConsultPage() {
  const [message, setMessage] = useState("");
  const [threadId, setThreadId] = useState("");
  const { events, running, finalResponse, error, run, cancel } = useConsultStream();

  const submit = () => {
    if (!message.trim() || running) return;
    const thread = threadId.trim() || `portal-${crypto.randomUUID().slice(0, 8)}`;
    setThreadId(thread);
    void run({ thread_id: thread, message: message.trim() });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold">提交问题</h1>
        <p className="text-sm text-muted-foreground">
          描述您遇到的问题，系统将进行安全检查和业务范围识别，并实时显示处理进度。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>问题描述</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            placeholder="例如：我本月被重复扣费了，请帮我核实并处理。"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            disabled={running}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">支持账户、账单、技术支持、SLA 与工单问题</span>
            {running ? (
              <Button variant="outline" size="sm" onClick={cancel}>
                停止
              </Button>
            ) : (
              <Button size="sm" onClick={submit} disabled={!message.trim()}>
                <Send className="h-3.5 w-3.5" />
                提交
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {(running || events.length > 0 || finalResponse || error) && (
        <Card>
          <CardHeader>
            <CardTitle>处理进度</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {events.length === 0 && running && <InlineLoader label="正在连接服务" />}
            <ol className="space-y-2">
              {events.map((event, index) => (
                <li key={index} className="flex gap-3 text-sm">
                  <span
                    className={cn(
                      "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                      event.event === "error" ? "bg-red-500" : "bg-accent",
                    )}
                  />
                  <div>
                    <p className="font-medium">{EVENT_LABELS[event.event] ?? event.event}</p>
                    <p className="text-xs text-muted-foreground">{eventDescription(event)}</p>
                  </div>
                </li>
              ))}
            </ol>

            {error && (
              <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                {error}
              </div>
            )}

            {finalResponse && (
              <div className="rounded-md border border-border bg-muted/40 p-4">
                <p className="mb-1 text-xs font-medium text-muted-foreground">处理结果</p>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{finalResponse}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
