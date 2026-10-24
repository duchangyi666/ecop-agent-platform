"use client";

import type { ReactNode } from "react";

import { useAuthorization } from "@/hooks/use-authorization";
import type { Permission } from "@/lib/permissions";

interface CanProps {
  permission: Permission;
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Reusable UI permission gate. This is intentionally UX-only; the backend
 * `require_permission` dependency remains the security boundary.
 */
export function Can({ permission, children, fallback = null }: CanProps) {
  const { can, isLoading } = useAuthorization();

  if (isLoading) return null;
  return can(permission) ? <>{children}</> : <>{fallback}</>;
}
