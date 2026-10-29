"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  FileText,
  ShieldCheck,
  Ticket as TicketIcon,
} from "lucide-react";
import { api } from "@/lib/api";
import { useApprovals, useKnowledgeDocuments, useTickets } from "@/hooks/use-data";
import { useAuthorization } from "@/hooks/use-authorization";
import { PERMISSIONS } from "@/lib/permissions";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, InlineLoader } from "@/components/ui/states";
import type { HealthResponse } from "@/lib/types";

export default function AdminOverviewPage() {
  const authorization = useAuthorization();
  const authorized = !authorization.isLoading && !authorization.error;
  const canReadTickets = authorized && authorization.can(PERMISSIONS.TICKET_READ);
  const canReadApprovals = authorized && authorization.can(PERMISSIONS.APPROVAL_READ);
  const canManageKnowledge = authorized && authorization.can(PERMISSIONS.KNOWLEDGE_INGEST)
    && authorization.can(PERMISSIONS.KNOWLEDGE_SEARCH);
  const canReadRuntime = authorized && authorization.can(PERMISSIONS.RUNTIME_READ);
  const health = useQuery({
    queryKey: ["healthz"],
    queryFn: () => api.get<HealthResponse>("/healthz"),
  });
  const tickets = useTickets(undefined, canReadTickets);
  const approvals = useApprovals("pending", canReadApprovals);
  const documents = useKnowledgeDocuments(canManageKnowledge);

  if (authorization.isLoading) return <InlineLoader label="正在确认权限" />;
  if (authorization.error) {
    return <ErrorState error={authorization.error} onRetry={() => authorization.refetch()} />;
  }

  const stats = [
    {
      label: "工单",
      value: tickets.data?.tickets.length ?? null,
      loading: tickets.isLoading,
      icon: TicketIcon,
      href: "/workspace",
      visible: canReadTickets,
    },
    {
      label: "待审批",
      value: approvals.data?.approvals.length ?? null,
      loading: approvals.isLoading,
      icon: ShieldCheck,
      href: "/workspace/approvals",
      visible: canReadApprovals,
    },
    {
      label: "知识文档",
      value: documents.data?.documents.length ?? null,
      loading: documents.isLoading,
      icon: FileText,
      href: "/admin/knowledge",
      visible: canManageKnowledge,
    },
    {
      label: "Runtime",
      value: "查看",
      loading: false,
      icon: Activity,
      href: "/admin/runtime",
      visible: canReadRuntime,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">管理控制台</h1>
        <p className="text-sm text-muted-foreground">平台运行状态、成本、评测与知识库管理。</p>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">后端服务</span>
        {health.isLoading ? (
          <StatusBadge value={null} label="检查中" />
        ) : health.data?.status === "ok" ? (
          <StatusBadge value="active" label="运行中" />
        ) : (
          <StatusBadge value="failed" label="异常" />
        )}
        {health.isError && (
          <span className="text-xs text-red-600">{health.error.message}</span>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.filter((stat) => stat.visible).map((stat) => (
          <Link key={stat.label} href={stat.href} className="group">
            <Card className="transition-colors group-hover:bg-muted/40">
              <CardContent className="flex items-center gap-3 p-4">
                <span className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                  <stat.icon className="h-5 w-5 text-muted-foreground" />
                </span>
                <div>
                  <p className="text-xs text-muted-foreground">{stat.label}</p>
                  {stat.loading ? (
                    <p className="h-5 w-8 animate-pulse rounded bg-muted" />
                  ) : (
                    <p className="text-xl font-semibold tabular-nums">
                      {typeof stat.value === "number" && stat.value >= 100 ? "100+" : stat.value}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {((canReadTickets && tickets.isError) || (canReadApprovals && approvals.isError) ||
        (canManageKnowledge && documents.isError)) && (
        <ErrorState
          error={(canReadTickets && tickets.error) || (canReadApprovals && approvals.error) ||
            (canManageKnowledge && documents.error)}
          onRetry={() => {
            if (canReadTickets && tickets.isError) tickets.refetch();
            if (canReadApprovals && approvals.isError) approvals.refetch();
            if (canManageKnowledge && documents.isError) documents.refetch();
          }}
        />
      )}
    </div>
  );
}
