"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useAuthStore } from "@/lib/auth-store";

export function IdentitySwitcher() {
  const identity = useAuthStore((state) => state.identity);

  if (!identity) {
    return (
      <Link
        href="/identity"
        className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-muted"
      >
        选择身份
      </Link>
    );
  }

  return (
    <Link
      href="/identity"
      className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 hover:bg-muted"
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-[10px] font-semibold text-accent-foreground">
        {identity.userName.slice(0, 1)}
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-xs font-medium">{identity.userName}</span>
        <span className="text-[10px] text-muted-foreground">{identity.tenantSlug}</span>
      </span>
      <ChevronRight className="h-3 w-3 text-muted-foreground" />
    </Link>
  );
}
