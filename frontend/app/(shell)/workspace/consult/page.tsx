"use client";

import { useState } from "react";
import { Play, Square } from "lucide-react";
import { useConsultStream } from "@/hooks/use-consult-stream";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/form";
import { Badge } from "@/components/ui/badge";
import { InlineLoader } from "@/components/ui/states";
import { cn } from "@/lib/cn";

const EVENT_TONES: Record<string, "blue" | "emerald" | "amber" | "red" | "neutral"> = {
  started: "blue",
  evidence: "blue",
  completed: "emerald",
  done: "emerald",
  error: "red",
};

export default function ConsultDebugPage() {
  const [threadId, setThreadId] = useState("");
  const [message, setMessage] = useState("");
  const { events, running, finalResponse, error, run, cancel } = useConsultStream();

  const submit = () => {
    if (!message.trim() || running) return;
    const thread = threadId.trim() || `debug-${crypto.randomUUID().slice(0, 8)}`;
    setThreadId(thread);
    void run({ thread_id: thread, message: message.trim() });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold">咨询调试</h1>
        <p className="text-sm text-muted-foreground">
          观察客服 Agent 全流程公开事件流（不包含内部推理链）。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>发送测试消息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            placeholder="线程 ID（留空自动生成）"
            value={threadId}
            onChange={(event) => setThreadId(event.target.value)}
            disabled={running}
          />
          <Textarea
            placeholder="输入客户问题，例如：我们企业账号被锁定了，请协助解锁。"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            disabled={running}
          />
          {running ? (
            <Button variant="outline" onClick={cancel}>
              <Square className="h-3.5 w-3.5" />
              停止
            </Button>
          ) : (
            <Button onClick={submit} disabled={!message.trim()}>
              <Play className="h-3.5 w-3.5" />
              运行
            </Button>
          )}
        </CardContent>
      </Card>

      {(running || events.length > 0 || finalResponse || error) && (
        <Card>
          <CardHeader>
            <CardTitle>事件流</CardTitle>
          </CardHeader>
          <CardContent>
            {events.length === 0 && running && <InlineLoader label="等待事件" />}
            <div className="space-y-2">
              {events.map((event, index) => (
                <div
                  key={index}
                  className="flex items-start gap-3 rounded-md border border-border p-2.5"
                >
                  <Badge tone={EVENT_TONES[event.event] ?? "neutral"}>{event.event}</Badge>
                  <pre className="min-w-0 flex-1 overflow-x-auto text-xs text-muted-foreground">
                    {JSON.stringify(event.data, null, 2)}
                  </pre>
                </div>
              ))}
              {error && (
                <div
                  className={cn(
                    "rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700",
                    "dark:border-red-900 dark:bg-red-950 dark:text-red-300",
                  )}
                >
                  {error}
                </div>
              )}
              {finalResponse && (
                <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
                  <p className="mb-1 text-xs font-medium">最终回复</p>
                  <p className="whitespace-pre-wrap leading-relaxed">{finalResponse}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
