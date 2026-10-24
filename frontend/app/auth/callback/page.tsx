"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { completeOidcLogin } from "@/lib/oidc";
import { useAuthStore } from "@/lib/auth-store";

export default function OIDCCallbackPage() {
  const router = useRouter();
  const setSession = useAuthStore((state) => state.setSession);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    let cancelled = false;
    const run = async () => {
      try {
        const session = await completeOidcLogin(window.location.search);
        if (cancelled) return;
        setSession(session.identity, session.accessToken);
        router.replace("/chat");
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "登录失败");
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [router, setSession]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 text-center shadow-sm">
        {error ? (
          <>
            <h1 className="text-base font-semibold text-red-600">登录失败</h1>
            <p className="mt-2 text-sm text-muted-foreground">{error}</p>
            <Link href="/login" className="mt-6 inline-block text-sm text-accent hover:underline">
              返回登录
            </Link>
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-accent" />
            <h1 className="mt-4 text-base font-semibold">正在完成登录</h1>
            <p className="mt-2 text-sm text-muted-foreground">正在校验企业身份并建立会话…</p>
          </>
        )}
      </div>
    </div>
  );
}
