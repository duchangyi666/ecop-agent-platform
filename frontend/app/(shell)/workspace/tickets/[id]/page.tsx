"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { useApprovals, useTicket, useUpdateTicket } from "@/hooks/use-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, InlineLoader } from "@/components/ui/states";
import { formatDateTime, ticketCategory, ticketPriority, ticketStatus } from "@/lib/format";

const STATUS_OPTIONS = [
  { value: "open", label: "待处理" },
  { value: "in_progress", label: "处理中" },
  { value: "pending_customer", label: "等待客户" },
  { value: "pending_approval", label: "等待审批" },
  { value: "escalated", label: "已升级" },
  { value: "resolved", label: "已解决" },
  { value: "closed", label: "已关闭" },
  { value: "cancelled", label: "已取消" },
];

export default function WorkspaceTicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticket = useTicket(params.id);
  const approvals = useApprovals();
  const updateTicket = useUpdateTicket();
  const [targetStatus, setTargetStatus] = useState("");

  if (ticket.isLoading) return <InlineLoader label="正在加载工单" />;
  if (ticket.isError || !ticket.data) {
    return <ErrorState error={ticket.error} onRetry={() => ticket.refetch()} />;
  }

  const detail = ticket.data;
  const t = detail.ticket;
  const relatedApproval = (approvals.data?.approvals ?? []).find(
    (approval) => approval.ticket_id === t.ticket_id,
  );

  const applyStatus = () => {
    if (!targetStatus || targetStatus === t.status) return;
    updateTicket.mutate(
      { ticketId: t.ticket_id, body: { status: targetStatus } },
      { onSuccess: () => setTargetStatus("") },
    );
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        href="/workspace"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        返回工单队列
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">{t.subject}</h1>
        <StatusBadge value={t.status} label={ticketStatus(t.status)} />
        {relatedApproval && (
          <Link href={`/workspace/approvals/${relatedApproval.approval_request_id}`}>
            <span className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
              <ShieldCheck className="h-3 w-3" />
              关联审批
            </span>
          </Link>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {ticketCategory(t.category)} · {ticketPriority(t.priority)} · 创建于{" "}
        {formatDateTime(t.created_at)}
      </p>

      <Card>
        <CardHeader>
          <CardTitle>更新工单状态</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-2">
          <Select value={targetStatus} onChange={(event) => setTargetStatus(event.target.value)}>
            <option value="">选择新状态…</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Button
            size="sm"
            onClick={applyStatus}
            disabled={!targetStatus || targetStatus === t.status || updateTicket.isPending}
            loading={updateTicket.isPending}
          >
            更新
          </Button>
          {updateTicket.isError && (
            <span className="text-xs text-red-600">{updateTicket.error.message}</span>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>消息</CardTitle>
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
          <CardTitle>事件记录</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-2">
            {detail.events.map((event) => (
              <li key={event.event_id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground" />
                <span className="text-muted-foreground">{ticketStatus(event.from_status)}</span>
                <span>→</span>
                <span className="font-medium">{ticketStatus(event.to_status)}</span>
                <span className="text-xs text-muted-foreground">{event.event_type}</span>
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
