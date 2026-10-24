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
  accessToken: string | null;
  _hasHydrated: boolean;
  setIdentity: (identity: Identity | null) => void;
  setSession: (identity: Identity, accessToken: string) => void;
  clear: () => void;
}

const STORAGE_KEY = "clouddesk-identity";

/**
 * Synchronously restore the persisted identity on module load (client only).
 * zustand's persist rehydrates asynchronously, which makes the first client
 * render report identity === null even when the user is signed in — causing
 * a misleading "正在确认身份" screen. Reading localStorage directly here keeps
 * the initial state correct and avoids that race entirely.
 */
function readInitialIdentity(): Identity | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { state?: { identity?: Identity | null } };
    return parsed.state?.identity ?? null;
  } catch {
    return null;
  }
}

function readInitialAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { state?: { accessToken?: string | null } };
    return parsed.state?.accessToken ?? null;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      identity: readInitialIdentity(),
      accessToken: readInitialAccessToken(),
      // On the server there is no localStorage; on the client the identity
      // above is already correct, so hydration is considered complete.
      _hasHydrated: typeof window !== "undefined",
      setIdentity: (identity) => set({ identity }),
      setSession: (identity, accessToken) => set({ identity, accessToken }),
      clear: () => set({ identity: null, accessToken: null }),
    }),
    {
      name: STORAGE_KEY,
      partialize: (state) => ({
        identity: state.identity,
        accessToken: state.accessToken,
      }),
    },
  ),
);

/** Bearer token when signed in through OIDC; dev headers otherwise. */
export function authHeaders(): Record<string, string> {
  const { identity, accessToken } = useAuthStore.getState();
  if (accessToken) {
    return { Authorization: `Bearer ${accessToken}` };
  }
  if (!identity) return {};
  return {
    "X-Tenant-Id": identity.tenantId,
    "X-Actor-Id": identity.userId,
    "X-Actor-Type": identity.actorType,
  };
}
