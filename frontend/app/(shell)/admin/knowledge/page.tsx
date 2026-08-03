"use client";

import { useState } from "react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import {
  useDeleteDocument,
  useIngestDocument,
  useKnowledgeDocuments,
  useReindexKnowledge,
} from "@/hooks/use-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";

export default function AdminKnowledgePage() {
  const documents = useKnowledgeDocuments();
  const ingest = useIngestDocument();
  const remove = useDeleteDocument();
  const reindex = useReindexKnowledge();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({
    external_document_id: "",
    title: "",
    source_uri: "",
    visibility: "tenant",
    content: "",
  });

  const submitIngest = () => {
    ingest.mutate(
      {
        thread_id: `admin-${crypto.randomUUID().slice(0, 8)}`,
        external_document_id: form.external_document_id.trim(),
        title: form.title.trim(),
        source_uri: form.source_uri.trim() || undefined,
        visibility: form.visibility as "tenant" | "public",
        content: form.content,
        chunk_size: 800,
        chunk_overlap: 80,
      },
      {
        onSuccess: () => {
          setDialogOpen(false);
          setForm({ external_document_id: "", title: "", source_uri: "", visibility: "tenant", content: "" });
        },
      },
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">知识库管理</h1>
          <p className="text-sm text-muted-foreground">管理知识文档、摄取与索引。</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => reindex.mutate()} loading={reindex.isPending}>
            <RefreshCw className="h-3.5 w-3.5" />
            重建索引
          </Button>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            摄取文档
          </Button>
        </div>
      </div>

      {reindex.data && (
        <p className="text-xs text-emerald-600">
          已重建 {reindex.data.document_count} 篇文档 / {reindex.data.chunk_count} 个分片。
        </p>
      )}

      <Card>
        <CardContent className="p-0">
          {documents.isLoading && <LoadingState rows={5} />}
          {documents.isError && <ErrorState error={documents.error} onRetry={() => documents.refetch()} />}
          {documents.data && documents.data.documents.length === 0 && (
            <div className="p-4">
              <EmptyState title="暂无知识文档" description="通过“摄取文档”添加企业知识。" />
            </div>
          )}
          {documents.data && documents.data.documents.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>标题</TableHead>
                  <TableHead>外部 ID</TableHead>
                  <TableHead>可见性</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>更新时间</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.data.documents.map((document) => (
                  <TableRow key={document.document_id}>
                    <TableCell className="font-medium">{document.title}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {document.external_document_id}
                    </TableCell>
                    <TableCell>{document.visibility}</TableCell>
                    <TableCell>
                      <StatusBadge value={document.status} label={document.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(document.updated_at)}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground hover:text-red-600"
                        onClick={() => remove.mutate(document.document_id)}
                        loading={remove.isPending}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title="摄取知识文档">
        <div className="space-y-3">
          <Field label="外部文档 ID">
            <Input
              value={form.external_document_id}
              onChange={(event) => setForm({ ...form, external_document_id: event.target.value })}
              placeholder="ext-refund-policy-v1"
            />
          </Field>
          <Field label="标题">
            <Input
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="退款政策"
            />
          </Field>
          <Field label="来源 URI">
            <Input
              value={form.source_uri}
              onChange={(event) => setForm({ ...form, source_uri: event.target.value })}
              placeholder="https://docs.example.com/refund-policy"
            />
          </Field>
          <Field label="可见性">
            <Select
              value={form.visibility}
              onChange={(event) => setForm({ ...form, visibility: event.target.value })}
            >
              <option value="tenant">tenant</option>
              <option value="public">public</option>
            </Select>
          </Field>
          <Field label="内容">
            <Textarea
              value={form.content}
              onChange={(event) => setForm({ ...form, content: event.target.value })}
              placeholder="文档正文内容…"
            />
          </Field>
          {ingest.isError && <p className="text-xs text-red-600">{ingest.error.message}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              size="sm"
              onClick={submitIngest}
              loading={ingest.isPending}
              disabled={!form.external_document_id.trim() || !form.title.trim() || !form.content.trim()}
            >
              摄取
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
