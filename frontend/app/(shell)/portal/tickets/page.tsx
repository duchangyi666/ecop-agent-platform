"use client";

import Link from "next/link";
import { useTickets } from "@/hooks/use-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatDateTime, ticketCategory, ticketPriority, ticketStatus } from "@/lib/format";

export default function PortalTicketsPage() {
  const tickets = useTickets();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">我的工单</h1>
        <p className="text-sm text-muted-foreground">您提交的工单与处理进度。</p>
      </div>

      {tickets.isLoading && <LoadingState rows={6} />}
      {tickets.isError && <ErrorState error={tickets.error} onRetry={() => tickets.refetch()} />}
      {tickets.data && tickets.data.tickets.length === 0 && (
        <EmptyState
          title="暂无工单"
          description="在“提交问题”页描述您的问题，处理后会生成工单记录。"
        />
      )}

      {tickets.data && tickets.data.tickets.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>全部工单（{tickets.data.tickets.length}）</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border">
              {tickets.data.tickets.map((ticket) => (
                <li key={ticket.ticket_id}>
                  <Link
                    href={`/portal/tickets/${ticket.ticket_id}`}
                    className="grid grid-cols-1 items-center gap-2 py-3 hover:bg-muted/50 sm:grid-cols-[1fr_auto_auto]"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{ticket.subject}</p>
                      <p className="text-xs text-muted-foreground">
                        {ticketCategory(ticket.category)} · {ticketPriority(ticket.priority)} ·{" "}
                        {formatDateTime(ticket.created_at)}
                      </p>
                    </div>
                    <StatusBadge value={ticket.status} label={ticketStatus(ticket.status)} />
                    <span className="text-xs text-muted-foreground sm:text-right">
                      {formatDateTime(ticket.updated_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
