"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Identity {
  tenantId: string;
  tenantSlug: string;
  userId: string;
  userName: string;
  actorType: string;
}

interface AuthState {
  identity: Identity | null;
  setIdentity: (identity: Identity | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      identity: null,
      setIdentity: (identity) => set({ identity }),
      clear: () => set({ identity: null }),
    }),
    { name: "clouddesk-identity" },
  ),
);

/** Dev-boundary auth headers. Production uses JWT Bearer. */
export function authHeaders(): Record<string, string> {
  const { identity } = useAuthStore.getState();
  if (!identity) return {};
  return {
    "X-Tenant-Id": identity.tenantId,
    "X-Actor-Id": identity.userId,
    "X-Actor-Type": identity.actorType,
  };
}
