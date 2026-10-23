"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Check, X } from "lucide-react";
import { useActOnApproval, useApproval } from "@/hooks/use-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/form";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, InlineLoader } from "@/components/ui/states";
import { approvalAction, approvalRole, approvalStatus, formatDateTime, formatMoney, riskLevel } from "@/lib/format";

export default function ApprovalDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const approval = useApproval(params.id);
  const actOnApproval = useActOnApproval();
  const [reason, setReason] = useState("");
  const [decision, setDecision] = useState<"approve" | "reject" | null>(null);

  if (approval.isLoading) return <InlineLoader label="正在加载审批" />;
  if (approval.isError || !approval.data) {
    return <ErrorState error={approval.error} onRetry={() => approval.refetch()} />;
  }

  const detail = approval.data;
  const a = detail.approval;
  const isPending = a.status === "pending";

  const submitDecision = () => {
    if (!decision) return;
    actOnApproval.mutate(
      {
        approvalId: a.approval_request_id,
        body: {
          thread_id: a.checkpoint_reference ?? `approval-${crypto.randomUUID().slice(0, 8)}`,
          approved: decision === "approve",
          reason: reason.trim() || (decision === "approve" ? "审批通过" : "审批拒绝"),
        },
      },
      {
        onSuccess: () => {
          setDecision(null);
          setReason("");
          approval.refetch();
          router.refresh();
        },
      },
    );
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        href="/workspace/approvals"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        返回审批列表
      </Link>

      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">{approvalAction(a.action)}</h1>
        <StatusBadge value={a.status} label={approvalStatus(a.status)} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>审批信息</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">金额</dt>
              <dd className="tabular-nums font-medium">{formatMoney(a.amount)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">风险等级</dt>
              <dd>{riskLevel(a.risk_level)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">审批角色</dt>
              <dd>{approvalRole(a.approval_role)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">关联工单</dt>
              <dd>{a.ticket_id ? "有" : "无"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">过期时间</dt>
              <dd>{formatDateTime(a.expires_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">操作次数</dt>
              <dd>{a.action_count}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {detail.actions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>操作记录</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {detail.actions.map((action) => (
                <li key={action.action_id} className="text-sm">
                  <p className="font-medium">{action.action}</p>
                  <p className="text-xs text-muted-foreground">{action.reason}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{formatDateTime(action.acted_at)}</p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {isPending && (
        <Card>
          <CardHeader>
            <CardTitle>审批决策</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              placeholder="审批备注（可选）"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              disabled={actOnApproval.isPending}
            />
            {actOnApproval.isError && (
              <p className="text-xs text-red-600">{actOnApproval.error.message}</p>
            )}
            <div className="flex gap-2">
              <Button
                variant="primary"
                onClick={() => setDecision("approve")}
                disabled={actOnApproval.isPending}
              >
                <Check className="h-4 w-4" />
                批准
              </Button>
              <Button
                variant="danger"
                onClick={() => setDecision("reject")}
                disabled={actOnApproval.isPending}
              >
                <X className="h-4 w-4" />
                拒绝
              </Button>
            </div>
            {decision && (
              <div className="rounded-md border border-border bg-muted/40 p-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  确认{decision === "approve" ? "批准" : "拒绝"}该请求？
                </p>
                <div className="flex gap-2">
                  <Button size="sm" onClick={submitDecision} loading={actOnApproval.isPending}>
                    确认
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDecision(null)}>
                    取消
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
