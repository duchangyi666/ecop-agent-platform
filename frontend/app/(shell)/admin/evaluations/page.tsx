"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { useEvaluationRuns, useRunEvaluation } from "@/hooks/use-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/form";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";

const DATASETS = [
  { value: "domain_classification", label: "业务范围分类" },
  { value: "intent_classification", label: "意图识别" },
  { value: "entity_extraction", label: "实体抽取" },
  { value: "security_detection", label: "安全风险检测" },
  { value: "retrieval", label: "知识检索" },
  { value: "refund_decision", label: "退款决策" },
  { value: "out_of_scope", label: "范围外问题" },
  { value: "response_quality", label: "回复质量" },
];

export default function EvaluationsPage() {
  const [dataset, setDataset] = useState("retrieval");
  const [limit, setLimit] = useState("5");
  const runs = useEvaluationRuns();
  const runEvaluation = useRunEvaluation();

  const submit = () => {
    runEvaluation.mutate({ dataset_code: dataset, limit: Number(limit) || 5 });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">评测</h1>
        <p className="text-sm text-muted-foreground">运行评测数据集并查看结果。</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>发起评测</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="w-56">
            <Field label="数据集">
              <Select value={dataset} onChange={(event) => setDataset(event.target.value)}>
                {DATASETS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="w-28">
            <Field label="限制用例数">
              <Input value={limit} onChange={(event) => setLimit(event.target.value)} />
            </Field>
          </div>
          <Button onClick={submit} loading={runEvaluation.isPending} disabled={runEvaluation.isPending}>
            <Play className="h-3.5 w-3.5" />
            运行
          </Button>
          {runEvaluation.isError && (
            <span className="text-xs text-red-600">{runEvaluation.error.message}</span>
          )}
        </CardContent>
      </Card>

      {runEvaluation.data && (
        <Card>
          <CardHeader>
            <CardTitle>最近结果：{runEvaluation.data.dataset_code}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-2 text-sm text-muted-foreground">
              {runEvaluation.data.case_count} 个用例 · 状态 {runEvaluation.data.status}
            </p>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
              {JSON.stringify(runEvaluation.data.metrics, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>运行历史</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {runs.isLoading && <LoadingState rows={4} />}
          {runs.isError && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
          {runs.data && runs.data.runs.length === 0 && (
            <div className="p-4">
              <EmptyState title="暂无评测记录" description="发起一次评测后结果会显示在这里。" />
            </div>
          )}
          {runs.data && runs.data.runs.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>状态</TableHead>
                  <TableHead>指标摘要</TableHead>
                  <TableHead>开始时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.data.runs.map((run) => (
                  <TableRow key={run.run_id}>
                    <TableCell>
                      <StatusBadge value={run.status} label={run.status} />
                    </TableCell>
                    <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                      {JSON.stringify(run.metrics)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(run.started_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
