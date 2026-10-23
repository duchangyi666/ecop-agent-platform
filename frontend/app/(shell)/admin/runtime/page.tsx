"use client";

import Link from "next/link";
import { useState } from "react";
import { useRuntimeAgents, useRuntimeCosts, useRuntimeTraces } from "@/hooks/use-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatMoney } from "@/lib/format";

const TABS = [
  { key: "traces", label: "Traces" },
  { key: "costs", label: "成本" },
  { key: "agents", label: "Agent" },
];

const ENTRYPOINT_LABELS: Record<string, string> = {
  "agent.customer_consultation": "客户咨询",
  "agent.refund": "退款流程",
  "agent.knowledge": "知识检索",
  "agent.knowledge.ingest": "知识摄取",
  "agent.ticket": "工单流程",
};

function traceLabel(trace: { trace_id: string; entrypoint: string }): string {
  const label = ENTRYPOINT_LABELS[trace.entrypoint] ?? trace.entrypoint;
  return `${label} · ${trace.trace_id.slice(0, 8)}`;
}

export default function RuntimePage() {
  const [tab, setTab] = useState("traces");
  const traces = useRuntimeTraces();
  const costs = useRuntimeCosts();
  const agents = useRuntimeAgents();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Runtime</h1>
        <p className="text-sm text-muted-foreground">Agent 运行轨迹、成本与可用 Agent 清单。</p>
      </div>

      <Tabs items={TABS} active={tab} onChange={setTab} />

      {tab === "traces" && (
        <Card>
          <CardContent className="p-0">
            {traces.isLoading && <LoadingState rows={6} />}
            {traces.isError && <ErrorState error={traces.error} onRetry={() => traces.refetch()} />}
            {traces.data && traces.data.traces.length === 0 && (
              <div className="p-4">
                <EmptyState title="暂无 Trace" description="咨询请求执行后会生成运行轨迹。" />
              </div>
            )}
            {traces.data && traces.data.traces.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Trace</TableHead>
                    <TableHead>入口</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead className="w-20 whitespace-nowrap">成本</TableHead>
                    <TableHead>开始时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {traces.data.traces.map((trace) => (
                    <TableRow key={trace.trace_id}>
                      <TableCell>
                        <Link
                          href={`/admin/runtime/${trace.trace_id}`}
                          className="font-medium hover:text-accent"
                        >
                          {traceLabel(trace)}
                        </Link>
                      </TableCell>
                      <TableCell>{trace.entrypoint}</TableCell>
                      <TableCell>
                        <StatusBadge value={trace.status} label={trace.status} />
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {Number(trace.total_cost) > 0 ? formatMoney(trace.total_cost) : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(trace.started_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {tab === "costs" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {costs.isLoading && <LoadingState rows={2} />}
          {costs.isError && <ErrorState error={costs.error} onRetry={() => costs.refetch()} />}
          {costs.data && (
            <>
              {[
                { label: "Trace 总数", value: String(costs.data.trace_count) },
                { label: "输入 Tokens", value: costs.data.total_input_tokens.toLocaleString() },
                { label: "输出 Tokens", value: costs.data.total_output_tokens.toLocaleString() },
                { label: "失败数", value: String(costs.data.failed_count) },
              ].map((item) => (
                <Card key={item.label}>
                  <CardHeader>
                    <CardTitle>{item.label}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-2xl font-semibold tabular-nums">{item.value}</p>
                  </CardContent>
                </Card>
              ))}
              <Card className="sm:col-span-2 lg:col-span-4">
                <CardHeader>
                  <CardTitle>总成本</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold tabular-nums">
                    {Number(costs.data.total_cost) > 0 ? formatMoney(costs.data.total_cost) : "—"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    当前未接入计价规则，Token 统计可用
                  </p>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      )}

      {tab === "agents" && (
        <Card>
          <CardContent className="p-0">
            {agents.isLoading && <LoadingState rows={4} />}
            {agents.isError && <ErrorState error={agents.error} onRetry={() => agents.refetch()} />}
            {agents.data && agents.data.agents.length === 0 && (
              <div className="p-4">
                <EmptyState title="暂无 Agent 定义" />
              </div>
            )}
            {agents.data && agents.data.agents.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>代码</TableHead>
                    <TableHead>名称</TableHead>
                    <TableHead>状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agents.data.agents.map((agent) => (
                    <TableRow key={agent.agent_id}>
                      <TableCell className="font-mono text-xs">{agent.agent_code}</TableCell>
                      <TableCell>{agent.name}</TableCell>
                      <TableCell>
                        <StatusBadge value={agent.status} label={agent.status} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
