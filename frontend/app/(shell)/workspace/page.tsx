"use client";

import Link from "next/link";
import { useState } from "react";
import { Search } from "lucide-react";
import { useTickets } from "@/hooks/use-data";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Tabs } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, ticketCategory, ticketPriority, ticketStatus } from "@/lib/format";

const STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "open", label: "待处理" },
  { key: "in_progress", label: "处理中" },
  { key: "pending_approval", label: "等待审批" },
  { key: "resolved", label: "已解决" },
  { key: "escalated", label: "已升级" },
];

export default function WorkspaceOverviewPage() {
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const tickets = useTickets(status === "all" ? undefined : status);

  const filtered = (tickets.data?.tickets ?? []).filter((ticket) =>
    ticket.subject.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">工单队列</h1>
          <p className="text-sm text-muted-foreground">处理客户工单、审批与知识检索。</p>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="w-64 pl-8"
            placeholder="搜索工单主题"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>

      <Tabs items={STATUS_TABS} active={status} onChange={setStatus} />

      {tickets.isLoading && <LoadingState rows={8} />}
      {tickets.isError && <ErrorState error={tickets.error} onRetry={() => tickets.refetch()} />}
      {tickets.data && filtered.length === 0 && (
        <EmptyState title="没有匹配的工单" description="调整筛选条件或搜索关键词。" />
      )}

      {filtered.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>主题</TableHead>
                  <TableHead>分类</TableHead>
                  <TableHead>优先级</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>更新于</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((ticket) => (
                  <TableRow key={ticket.ticket_id}>
                    <TableCell>
                      <Link href={`/workspace/tickets/${ticket.ticket_id}`} className="font-medium hover:text-accent">
                        {ticket.subject}
                      </Link>
                    </TableCell>
                    <TableCell>{ticketCategory(ticket.category)}</TableCell>
                    <TableCell>{ticketPriority(ticket.priority)}</TableCell>
                    <TableCell>
                      <StatusBadge value={ticket.status} label={ticketStatus(ticket.status)} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(ticket.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
