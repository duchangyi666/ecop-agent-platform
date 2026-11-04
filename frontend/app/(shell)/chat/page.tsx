"use client";

import Link from "next/link";
import { ChatWindow } from "@/components/chat/chat-window";
import { EmptyState, ErrorState, InlineLoader } from "@/components/ui/states";
import { useAuthorization } from "@/hooks/use-authorization";
import { PERMISSIONS } from "@/lib/permissions";

export default function ChatPage() {
  const { can, isLoading, error, refetch } = useAuthorization();

  if (isLoading) return <InlineLoader label="正在确认权限" />;
  if (error) return <div className="p-6"><ErrorState error={error} onRetry={refetch} /></div>;
  if (!can(PERMISSIONS.CUSTOMER_CONSULT)) {
    return (
      <div className="p-6">
        <EmptyState
          title="当前身份没有客服咨询权限"
          description="请切换身份，或使用当前身份可访问的功能。"
          action={can(PERMISSIONS.KNOWLEDGE_SEARCH) ? (
            <Link href="/workspace/knowledge" className="mt-2 text-sm text-accent hover:underline">
              前往知识库检索
            </Link>
          ) : null}
        />
      </div>
    );
  }
  return <ChatWindow />;
}
