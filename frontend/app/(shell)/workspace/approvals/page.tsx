"use client";

import Link from "next/link";
import { useState } from "react";
import { useApprovals } from "@/hooks/use-data";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { approvalAction, approvalRole, approvalStatus, formatDateTime, formatMoney, riskLevel } from "@/lib/format";

const STATUS_TABS = [
  { key: "pending", label: "待审批" },
  { key: "all", label: "全部" },
  { key: "approved", label: "已批准" },
  { key: "rejected", label: "已拒绝" },
  { key: "expired", label: "已过期" },
];

export default function ApprovalsPage() {
  const [status, setStatus] = useState("pending");
  const approvals = useApprovals(status === "all" ? undefined : status);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">审批</h1>
        <p className="text-sm text-muted-foreground">退款与高风险操作的审批队列。</p>
      </div>

      <Tabs items={STATUS_TABS} active={status} onChange={setStatus} />

      {approvals.isLoading && <LoadingState rows={6} />}
      {approvals.isError && <ErrorState error={approvals.error} onRetry={() => approvals.refetch()} />}
      {approvals.data && approvals.data.approvals.length === 0 && (
        <EmptyState title="没有待审批的请求" description="新的审批请求会出现在这里。" />
      )}

      {approvals.data && approvals.data.approvals.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>操作</TableHead>
                  <TableHead>金额</TableHead>
                  <TableHead>风险</TableHead>
                  <TableHead>审批角色</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>过期时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {approvals.data.approvals.map((approval) => (
                  <TableRow key={approval.approval_request_id}>
                    <TableCell className="font-medium">{approvalAction(approval.action)}</TableCell>
                    <TableCell className="tabular-nums">{formatMoney(approval.amount)}</TableCell>
                    <TableCell>{riskLevel(approval.risk_level)}</TableCell>
                    <TableCell>{approvalRole(approval.approval_role)}</TableCell>
                    <TableCell>
                      <StatusBadge value={approval.status} label={approvalStatus(approval.status)} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(approval.expires_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Link
                        href={`/workspace/approvals/${approval.approval_request_id}`}
                        className="text-xs font-medium text-accent hover:underline"
                      >
                        审批
                      </Link>
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
