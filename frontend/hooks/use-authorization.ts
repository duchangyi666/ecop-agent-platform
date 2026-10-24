"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export interface AuthorizationSnapshot {
  tenantId: string;
  userId: string;
  displayName: string;
  roles: string[];
  permissions: string[];
}

export function useAuthorization() {
  const identity = useAuthStore((state) => state.identity);
  const accessToken = useAuthStore((state) => state.accessToken);

  const query = useQuery({
    queryKey: [
      "auth",
      "me",
      identity?.tenantId,
      identity?.userId,
      accessToken ? "bearer" : "dev",
    ],
    queryFn: () => api.get<AuthorizationSnapshot>("/api/v1/auth/me"),
    enabled: Boolean(identity),
    staleTime: 60_000,
  });

  const permissions = query.data?.permissions ?? [];

  return {
    roles: query.data?.roles ?? [],
    permissions,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
    can: (permission: string) => permissions.includes(permission),
  };
}
