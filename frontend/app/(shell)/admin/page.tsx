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
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState } from "@/components/ui/states";
import type { HealthResponse } from "@/lib/types";

export default function AdminOverviewPage() {
  const health = useQuery({
    queryKey: ["healthz"],
    queryFn: () => api.get<HealthResponse>("/healthz"),
  });
  const tickets = useTickets();
  const approvals = useApprovals();
  const documents = useKnowledgeDocuments();

  const stats = [
    {
      label: "工单",
      value: tickets.data?.tickets.length ?? null,
      loading: tickets.isLoading,
      icon: TicketIcon,
      href: "/workspace",
    },
    {
      label: "待审批",
      value: approvals.data?.approvals.length ?? null,
      loading: approvals.isLoading,
      icon: ShieldCheck,
      href: "/workspace/approvals",
    },
    {
      label: "知识文档",
      value: documents.data?.documents.length ?? null,
      loading: documents.isLoading,
      icon: FileText,
      href: "/admin/knowledge",
    },
    {
      label: "Runtime",
      value: "查看",
      loading: false,
      icon: Activity,
      href: "/admin/runtime",
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
        {stats.map((stat) => (
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
                      {typeof stat.value === "number" ? stat.value : stat.value}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {(tickets.isError || approvals.isError || documents.isError) && (
        <ErrorState
          error={tickets.error ?? approvals.error ?? documents.error}
          onRetry={() => {
            tickets.refetch();
            approvals.refetch();
            documents.refetch();
          }}
        />
      )}
    </div>
  );
}
