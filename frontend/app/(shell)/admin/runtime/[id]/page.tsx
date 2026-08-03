"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useRuntimeTrace } from "@/hooks/use-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { ErrorState, InlineLoader } from "@/components/ui/states";
import { formatDateTime, formatMoney } from "@/lib/format";

export default function RuntimeTraceDetailPage() {
  const params = useParams<{ id: string }>();
  const trace = useRuntimeTrace(params.id);

  if (trace.isLoading) return <InlineLoader label="正在加载 Trace" />;
  if (trace.isError || !trace.data) {
    return <ErrorState error={trace.error} onRetry={() => trace.refetch()} />;
  }

  const t = trace.data.trace;
  const totalMs = trace.data.spans.reduce((sum, span) => sum + (span.duration_ms ?? 0), 0);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        href="/admin/runtime"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        返回 Runtime
      </Link>

      <div className="flex items-center gap-3">
        <h1 className="font-mono text-lg font-semibold">{t.trace_key}</h1>
        <StatusBadge value={t.status} label={t.status} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>概览</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">入口</dt>
              <dd>{t.entrypoint}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">成本</dt>
              <dd className="tabular-nums">{formatMoney(t.total_cost)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">开始时间</dt>
              <dd>{formatDateTime(t.started_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Span 数</dt>
              <dd>{trace.data.spans.length}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">总耗时</dt>
              <dd className="tabular-nums">{(totalMs / 1000).toFixed(2)}s</dd>
            </div>
          </dl>
          {t.error_summary && (
            <p className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              {t.error_summary}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Spans</CardTitle>
        </CardHeader>
        <CardContent>
          {trace.data.spans.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">暂无 Span</p>
          ) : (
            <ul className="divide-y divide-border">
              {trace.data.spans.map((span) => (
                <li key={span.span_id} className="py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{span.node_name}</span>
                    <StatusBadge value={span.status} label={span.status} />
                    <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                      {span.duration_ms !== null ? `${(span.duration_ms / 1000).toFixed(2)}s` : "-"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{span.output_summary}</p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
