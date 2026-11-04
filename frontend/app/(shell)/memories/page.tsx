"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthorization } from "@/hooks/use-authorization";
import { useAuthStore } from "@/lib/auth-store";
import { api } from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import { EmptyState, ErrorState, InlineLoader } from "@/components/ui/states";

interface MemoryItem {
  memory_id: string;
  memory_type: string;
  content: string;
  created_at: string;
  last_active_at: string;
  expires_at: string;
}

const labels: Record<string, string> = {
  language_preference: "语言偏好",
  timezone_preference: "时区偏好",
  user_preference: "使用偏好",
};

function MemoryList({ tenantId, userId }: { tenantId: string; userId: string }) {
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const queryKey = ["memories", tenantId, userId];
  const query = useQuery({
    queryKey: [...queryKey, offset],
    queryFn: () => api.get<{ memories: MemoryItem[]; next_offset: number | null }>("/api/v1/memories", { limit: 50, offset }),
  });
  const deletion = useMutation({
    mutationFn: (id: string) => api.del<void>(`/api/v1/memories/${id}`),
    onSuccess: () => { setOffset(0); return client.invalidateQueries({ queryKey }); },
  });

  const correction = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) => api.patch<MemoryItem>(`/api/v1/memories/${id}`, { value }),
    onSuccess: () => { setOffset(0); return client.invalidateQueries({ queryKey }); },
  });

  const settingsKey = ["memory-settings", tenantId, userId];
  const settings = useQuery({ queryKey: settingsKey, queryFn: () => api.get<{ enabled: boolean }>("/api/v1/memories/settings/current") });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api.patch<{ enabled: boolean }>("/api/v1/memories/settings/current", { enabled }),
    onMutate: async (enabled) => {
      await client.cancelQueries({ queryKey: settingsKey });
      const previous = client.getQueryData<{ enabled: boolean }>(settingsKey);
      client.setQueryData(settingsKey, { enabled });
      return { previous };
    },
    onError: (_error, _enabled, context) => {
      if (context?.previous) client.setQueryData(settingsKey, context.previous);
    },
    onSettled: () => client.invalidateQueries({ queryKey: settingsKey }),
  });

  if (query.isLoading) return <InlineLoader label="正在读取记忆" />;
  if (query.error) return <ErrorState error={query.error} onRetry={query.refetch} />;
  const memories = query.data?.memories ?? [];

  return (
    <div className="space-y-4">
      <section className="rounded-lg border p-4 space-y-2">
        <label className="flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" checked={toggle.isPending ? toggle.variables : settings.data?.enabled ?? false} disabled={!settings.data || toggle.isPending}
            onChange={(event) => toggle.mutate(event.target.checked)} />启用长期记忆
        </label>
        <p className="text-sm text-muted-foreground">关闭后停止记录和使用长期偏好，已有记忆仍可查看或删除。当前会话历史不受此开关控制。</p>
        {settings.error && <ErrorState error={settings.error} onRetry={settings.refetch} />}
        {toggle.error && <p role="alert" className="text-sm">设置未保存，请重试。</p>}
      </section>
      {deletion.error && <ErrorState error={deletion.error} onRetry={() => { if (deletion.variables) deletion.mutate(deletion.variables); }} />}
      {correction.error && <ErrorState error={correction.error} onRetry={() => { if (correction.variables) correction.mutate(correction.variables); }} />}
      {correction.isSuccess && <p role="status" className="text-sm text-muted-foreground">记忆已更新，后续对话将使用新偏好。</p>}
      {deletion.isSuccess && <p role="status" className="text-sm text-muted-foreground">记忆已删除，后续对话将不再召回。</p>}
      {memories.length === 0 ? <EmptyState title="暂无记忆" description="明确表达的语言、时区和使用偏好会显示在这里。" /> : (
        <ul className="space-y-3">
          {memories.map((memory) => (
            <li key={memory.memory_id} className="rounded-lg border bg-card p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 space-y-2">
                  <h2 className="text-sm font-medium">{labels[memory.memory_type] ?? "历史偏好"}</h2>
                  <p className="break-words text-sm">{memory.content === "preferred_language=zh" ? "使用中文" : memory.content === "preferred_language=en" ? "使用英文" : memory.content.replace(/^(preference|timezone)=/, "")}</p>
                  <p className="text-xs text-muted-foreground">最近活跃：{new Date(memory.last_active_at).toLocaleString()} · 到期：{new Date(memory.expires_at).toLocaleDateString()}</p>
                </div>
                <button type="button" disabled={!settings.data?.enabled || deletion.isPending || correction.isPending} className="shrink-0 rounded border px-3 py-1 text-sm disabled:opacity-50"
                  onClick={() => {
                    const current = memory.content.replace(/^(preferred_language|preference|timezone)=/, "");
                    const display = memory.memory_type === "language_preference" ? (current === "zh" ? "中文" : "英文") : current;
                    const hint = memory.memory_type === "language_preference" ? "修改语言：中文或英文" : memory.memory_type === "timezone_preference" ? "修改时区，例如 Asia/Shanghai" : "修改使用偏好";
                    const input = window.prompt(hint, display)?.trim();
                    const value = memory.memory_type === "language_preference" ? (input === "中文" ? "zh" : input === "英文" ? "en" : input) : input;
                    if (value && value !== current) correction.mutate({ id: memory.memory_id, value });
                  }}>修改</button>
                <button type="button" disabled={deletion.isPending || correction.isPending} className="shrink-0 rounded border px-3 py-1 text-sm disabled:opacity-50"
                  onClick={() => {
                    if (window.confirm("删除这条记忆？后续对话将不再使用它。")) deletion.mutate(memory.memory_id);
                  }}>删除</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <nav aria-label="记忆分页" className="flex items-center gap-4 text-sm">
        <button type="button" disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 50))}>上一页</button>
        <span>第 {Math.floor(offset / 50) + 1} 页</span>
        <button type="button" disabled={query.data?.next_offset == null || query.isFetching} onClick={() => { if (query.data?.next_offset != null) setOffset(query.data.next_offset); }}>下一页</button>
      </nav>
    </div>
  );
}

export default function MemoriesPage() {
  const identity = useAuthStore((state) => state.identity);
  const { can, isLoading, error, refetch } = useAuthorization();
  if (isLoading) return <InlineLoader label="正在确认权限" />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!identity || !can(PERMISSIONS.CUSTOMER_CONSULT)) return <EmptyState title="当前身份没有记忆管理权限" />;
  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 p-6">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold">我的记忆</h1>
        <p className="text-sm text-muted-foreground">管理用于个性化回答的历史偏好。删除后不再用于后续召回，已经开始的回答可能仍包含该偏好。</p>
      </header>
      <MemoryList key={`${identity.tenantId}:${identity.userId}`} tenantId={identity.tenantId} userId={identity.userId} />
    </main>
  );
}
