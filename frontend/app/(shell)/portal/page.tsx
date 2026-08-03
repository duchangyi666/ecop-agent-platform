"use client";

import Link from "next/link";
import { ArrowRight, MessageSquare, Ticket as TicketIcon } from "lucide-react";
import { useConversations, useTickets } from "@/hooks/use-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { conversationStatus, formatDateTime, ticketStatus } from "@/lib/format";

export default function PortalOverviewPage() {
  const conversations = useConversations();
  const tickets = useTickets();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold">客户门户</h1>
          <p className="text-sm text-muted-foreground">查看工单进度、历史会话，或提交新问题。</p>
        </div>
        <Link href="/portal/consult">
          <Button>
            <MessageSquare className="h-4 w-4" />
            提交问题
          </Button>
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>我的工单</CardTitle>
            <Link href="/portal/tickets" className="text-xs text-muted-foreground hover:text-foreground">
              查看全部
            </Link>
          </CardHeader>
          <CardContent>
            {tickets.isLoading && <LoadingState rows={3} />}
            {tickets.isError && <ErrorState error={tickets.error} onRetry={() => tickets.refetch()} />}
            {tickets.data && tickets.data.tickets.length === 0 && (
              <EmptyState title="暂无工单" description="提交问题后生成的工单会显示在这里。" />
            )}
            {tickets.data && tickets.data.tickets.length > 0 && (
              <ul className="divide-y divide-border">
                {tickets.data.tickets.slice(0, 5).map((ticket) => (
                  <li key={ticket.ticket_id}>
                    <Link
                      href={`/portal/tickets/${ticket.ticket_id}`}
                      className="flex items-center gap-3 py-2.5 hover:bg-muted/50"
                    >
                      <TicketIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-sm">{ticket.subject}</span>
                      <StatusBadge value={ticket.status} label={ticketStatus(ticket.status)} />
                      <span className="hidden text-xs text-muted-foreground sm:inline">
                        {formatDateTime(ticket.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>最近会话</CardTitle>
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {conversations.isLoading && <LoadingState rows={3} />}
            {conversations.isError && (
              <ErrorState error={conversations.error} onRetry={() => conversations.refetch()} />
            )}
            {conversations.data && conversations.data.conversations.length === 0 && (
              <EmptyState title="暂无会话" description="与客服的交流记录会显示在这里。" />
            )}
            {conversations.data && conversations.data.conversations.length > 0 && (
              <ul className="divide-y divide-border">
                {conversations.data.conversations.slice(0, 5).map((conversation) => (
                  <li key={conversation.conversation_id} className="flex items-center gap-3 py-2.5">
                    <span className="min-w-0 flex-1 truncate text-sm">{conversation.subject}</span>
                    <StatusBadge
                      value={conversation.status}
                      label={conversationStatus(conversation.status)}
                    />
                    <span className="hidden text-xs text-muted-foreground sm:inline">
                      {formatDateTime(conversation.started_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
