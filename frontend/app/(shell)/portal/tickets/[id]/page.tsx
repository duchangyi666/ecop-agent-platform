"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useTicket } from "@/hooks/use-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, InlineLoader } from "@/components/ui/states";
import { formatDateTime, ticketCategory, ticketPriority, ticketStatus } from "@/lib/format";

export default function PortalTicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticket = useTicket(params.id);

  if (ticket.isLoading) return <InlineLoader label="正在加载工单" />;
  if (ticket.isError || !ticket.data) {
    return <ErrorState error={ticket.error} onRetry={() => ticket.refetch()} />;
  }

  const detail = ticket.data;
  const t = detail.ticket;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link href="/portal/tickets" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" />
        返回工单列表
      </Link>

      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">{t.subject}</h1>
          <StatusBadge value={t.status} label={ticketStatus(t.status)} />
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {ticketCategory(t.category)} · {ticketPriority(t.priority)} · 创建于{" "}
          {formatDateTime(t.created_at)}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>处理记录</CardTitle>
        </CardHeader>
        <CardContent>
          {detail.messages.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">暂无消息</p>
          ) : (
            <ul className="space-y-3">
              {detail.messages.map((message) => (
                <li key={message.message_id} className="text-sm">
                  <p className="whitespace-pre-wrap leading-relaxed">{message.body}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {message.author_id ? "客服" : "系统"} · {formatDateTime(message.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>状态时间线</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2">
            {detail.events.map((event) => (
              <li key={event.event_id} className="flex items-center gap-3 text-sm">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground" />
                <span className="text-muted-foreground">{ticketStatus(event.from_status)}</span>
                <span>→</span>
                <span className="font-medium">{ticketStatus(event.to_status)}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {formatDateTime(event.occurred_at)}
                </span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
