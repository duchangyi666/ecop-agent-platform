"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronRight, Loader2, User } from "lucide-react";
import { api } from "@/lib/api";
import type { TenantListResponse, TenantUsersResponse } from "@/lib/types";
import { useAuthStore } from "@/lib/auth-store";
import { ErrorState, InlineLoader } from "@/components/ui/states";
import { cn } from "@/lib/cn";

/** Inline tenant + user picker; stores the dev-boundary identity. */
export function IdentityPanel() {
  const router = useRouter();
  const setIdentity = useAuthStore((state) => state.setIdentity);
  const [selectedTenant, setSelectedTenant] = useState<string | null>(null);

  const tenantsQuery = useQuery({
    queryKey: ["identity", "tenants"],
    queryFn: () => api.get<TenantListResponse>("/api/v1/identity/tenants", { limit: 200 }),
  });

  const usersQuery = useQuery({
    queryKey: ["identity", "users", selectedTenant],
    queryFn: () =>
      api.get<TenantUsersResponse>(`/api/v1/identity/tenants/${selectedTenant}/users`, {
        limit: 500,
      }),
    enabled: Boolean(selectedTenant),
  });

  const selectUser = (tenant: { id: string; slug: string }, userId: string, userName: string) => {
    setIdentity({
      tenantId: tenant.id,
      tenantSlug: tenant.slug,
      userId,
      userName,
      actorType: "user",
    });
    router.push("/chat");
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-foreground">
          CD
        </span>
        <div>
          <h1 className="text-lg font-semibold">CloudDesk 企业客户运营平台</h1>
          <p className="text-xs text-muted-foreground">选择开发环境身份以进入对应工作台</p>
        </div>
      </div>

      <div className="w-full max-w-md rounded-lg border border-border bg-card shadow-sm">
        {tenantsQuery.isLoading && <InlineLoader label="正在加载租户" />}
        {tenantsQuery.isError && (
          <div className="p-4">
            <ErrorState error={tenantsQuery.error} onRetry={() => tenantsQuery.refetch()} />
          </div>
        )}
        {tenantsQuery.data && (
          <ul className="max-h-96 divide-y divide-border overflow-auto">
            {tenantsQuery.data.tenants.map((tenant) => {
              const expanded = selectedTenant === tenant.id;
              return (
                <li key={tenant.id}>
                  <button
                    onClick={() => setSelectedTenant(expanded ? null : tenant.id)}
                    className="flex w-full items-center gap-2.5 px-4 py-3 text-left text-sm hover:bg-muted/50"
                  >
                    <Building2 className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium">{tenant.slug}</span>
                    <span className="flex-1 truncate text-xs text-muted-foreground">
                      {tenant.name}
                    </span>
                    <ChevronRight
                      className={cn(
                        "h-4 w-4 text-muted-foreground transition-transform",
                        expanded && "rotate-90",
                      )}
                    />
                  </button>
                  {expanded && (
                    <div className="border-t border-border bg-muted/30">
                      {usersQuery.isLoading && (
                        <div className="flex items-center gap-2 px-6 py-3 text-xs text-muted-foreground">
                          <Loader2 className="h-3 w-3 animate-spin" /> 正在加载用户
                        </div>
                      )}
                      {usersQuery.isError && (
                        <div className="px-6 py-3">
                          <ErrorState error={usersQuery.error} />
                        </div>
                      )}
                      <ul className="divide-y divide-border/60">
                        {usersQuery.data?.users.map((user) => (
                          <li key={user.id}>
                            <button
                              onClick={() =>
                                selectUser(tenant, user.id, user.display_name || user.email)
                              }
                              className="flex w-full items-center gap-2.5 px-6 py-2.5 text-left text-sm hover:bg-muted"
                            >
                              <User className="h-3.5 w-3.5 text-muted-foreground" />
                              <span>{user.display_name}</span>
                              <span className="ml-auto text-xs text-muted-foreground">
                                {user.email}
                              </span>
                            </button>
                          </li>
                        ))}
                        {usersQuery.data?.users.length === 0 && (
                          <li className="px-6 py-3 text-xs text-muted-foreground">该租户暂无用户</li>
                        )}
                      </ul>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <p className="max-w-md text-center text-xs text-muted-foreground">
        开发环境身份沿用请求头边界（X-Tenant-Id / X-Actor-Id / X-Actor-Type），生产环境将使用 JWT / OAuth。
      </p>
    </div>
  );
}
