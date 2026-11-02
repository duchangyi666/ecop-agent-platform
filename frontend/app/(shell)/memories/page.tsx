"use client";

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
  const queryKey = ["memories", tenantId, userId];
  const query = useQuery({
    queryKey,
    queryFn: () => api.get<{ memories: MemoryItem[] }>("/api/v1/memories", { limit: 100 }),
  });
  const deletion = useMutation({
    mutationFn: (id: string) => api.del<void>(`/api/v1/memories/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey }),
  });

  if (query.isLoading) return <InlineLoader label="正在读取记忆" />;
  if (query.error) return <ErrorState error={query.error} onRetry={query.refetch} />;
  const memories = query.data?.memories ?? [];

  return (
    <div className="space-y-4">
      {deletion.error && <ErrorState error={deletion.error} onRetry={() => { if (deletion.variables) deletion.mutate(deletion.variables); }} />}
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
                <button type="button" disabled={deletion.isPending} className="shrink-0 rounded border px-3 py-1 text-sm disabled:opacity-50"
                  onClick={() => {
                    if (window.confirm("删除这条记忆？后续对话将不再使用它。")) deletion.mutate(memory.memory_id);
                  }}>删除</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {memories.length === 100 && <p className="text-sm text-muted-foreground">当前显示最近的 100 条记忆，删除后可查看更早的记录。</p>}
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
