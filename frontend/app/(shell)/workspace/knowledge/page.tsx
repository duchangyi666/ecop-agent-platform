"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { useKnowledgeSearch } from "@/hooks/use-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { EmptyState, ErrorState, InlineLoader } from "@/components/ui/states";

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const search = useKnowledgeSearch(submitted, submitted.length > 0);

  const runSearch = () => {
    if (query.trim()) setSubmitted(query.trim());
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold">知识库检索</h1>
        <p className="text-sm text-muted-foreground">
          基于企业知识库检索退款政策、SLA 与产品文档。
        </p>
      </div>

      <div className="flex gap-2">
        <Input
          placeholder="例如：重复扣费如何申请退款？"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && runSearch()}
        />
        <Button onClick={runSearch} disabled={!query.trim()}>
          <Search className="h-4 w-4" />
          检索
        </Button>
      </div>

      {search.isLoading && <InlineLoader label="正在检索知识库" />}
      {search.isError && <ErrorState error={search.error} onRetry={() => search.refetch()} />}
      {search.isSuccess && search.data.results.length === 0 && (
        <EmptyState title="未找到相关文档" description="请尝试更换关键词。" />
      )}

      {search.data && search.data.results.length > 0 && (
        <div className="space-y-3">
          {search.data.results.map((result) => (
            <Card key={result.document_id}>
              <CardHeader className="flex-row items-start justify-between">
                <CardTitle>{result.title}</CardTitle>
                {result.score !== null && result.score !== undefined && (
                  <span className="tabular-nums text-xs text-muted-foreground">
                    分数 {result.score.toFixed(3)}
                  </span>
                )}
              </CardHeader>
              <CardContent>
                {result.content_snippet ? (
                  <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                    {result.content_snippet}
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">{result.external_document_id}</p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
