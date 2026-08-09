"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Identity {
  tenantId: string;
  tenantSlug: string;
  userId: string;
  userName: string;
  actorType: string;
  /** Signed JWT from login/register; when present it takes precedence over the dev headers. */
  accessToken?: string;
}

interface AuthState {
  identity: Identity | null;
  _hasHydrated: boolean;
  setIdentity: (identity: Identity | null) => void;
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

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      identity: readInitialIdentity(),
      // On the server there is no localStorage; on the client the identity
      // above is already correct, so hydration is considered complete.
      _hasHydrated: typeof window !== "undefined",
      setIdentity: (identity) => set({ identity }),
      clear: () => set({ identity: null }),
    }),
    {
      name: STORAGE_KEY,
      partialize: (state) => ({ identity: state.identity }),
    },
  ),
);

/**
 * Request headers for API calls. A signed Bearer token (from login/register)
 * takes precedence; the X-* dev-boundary headers are the fallback for local
 * development without a JWT.
 */
export function authHeaders(): Record<string, string> {
  const { identity } = useAuthStore.getState();
  if (!identity) return {};
  const headers: Record<string, string> = {};
  if (identity.accessToken) {
    headers["Authorization"] = `Bearer ${identity.accessToken}`;
  } else {
    headers["X-Tenant-Id"] = identity.tenantId;
    headers["X-Actor-Id"] = identity.userId;
    headers["X-Actor-Type"] = identity.actorType;
  }
  return headers;
}
