import type { ReactNode } from "react";
import { CircleAlert, Inbox, KeyRound, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

export function LoadingState({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border py-12 text-center">
      <Inbox className="h-8 w-8 text-muted-foreground" />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-sm text-xs text-muted-foreground">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : "发生未知错误";
  const code = error instanceof ApiError ? error.code : undefined;
  const requestId = error instanceof ApiError ? error.requestId : undefined;
  const isForbidden = error instanceof ApiError && error.status === 403;

  if (isForbidden) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-border py-12 text-center">
        <KeyRound className="h-8 w-8 text-amber-500" />
        <p className="text-sm font-medium">权限不足</p>
        <p className="max-w-sm text-xs text-muted-foreground">
          当前身份没有执行该操作的权限，请在右上角切换身份后重试。
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-border py-12 text-center">
      <CircleAlert className="h-8 w-8 text-red-500" />
      <p className="text-sm font-medium">{message}</p>
      <p className="text-xs text-muted-foreground">
        {code ? `code: ${code}` : "请稍后重试"}
        {requestId ? ` · request_id: ${requestId}` : ""}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 rounded-md border border-border px-3 py-1 text-xs hover:bg-muted"
        >
          重试
        </button>
      )}
    </div>
  );
}

export function InlineLoader({ label = "加载中" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}
