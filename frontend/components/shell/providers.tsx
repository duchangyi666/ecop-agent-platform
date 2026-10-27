"use client";

import { useEffect, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "@/lib/auth-store";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  useEffect(() => useAuthStore.subscribe((current, previous) => {
    const next = current.identity;
    const prior = previous.identity;
    if (
      next?.tenantId !== prior?.tenantId ||
      next?.userId !== prior?.userId ||
      next?.actorType !== prior?.actorType ||
      current.accessToken !== previous.accessToken
    ) {
      // Query keys in the consoles are shared; discard all cached results
      // synchronously before the new identity can render them.
      queryClient.clear();
    }
  }), [queryClient]);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
