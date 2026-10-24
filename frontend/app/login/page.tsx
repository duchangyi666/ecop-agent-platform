"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Loader2, LogIn, ShieldCheck } from "lucide-react";
import { beginOidcLogin } from "@/lib/oidc";
import { useAuthStore } from "@/lib/auth-store";

export default function LoginPage() {
  const router = useRouter();
  const identity = useAuthStore((state) => state.identity);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (identity) router.replace("/chat");
  }, [identity, router]);

  const login = async () => {
    setLoading(true);
    setError(null);
    try {
      await beginOidcLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-foreground">
            CD
          </span>
          <div>
            <h1 className="text-lg font-semibold">CloudDesk 企业登录</h1>
            <p className="text-xs text-muted-foreground">使用企业身份登录客户运营平台</p>
          </div>
        </div>

        <button
          onClick={login}
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
          {loading ? "正在跳转…" : "使用企业账号登录"}
        </button>

        {error && (
          <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        )}

        <div className="mt-6 flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>
            登录由企业 IdP 完成，平台不保存企业密码。当前本地环境使用 Dex 作为 OIDC
            提供方，生产环境可切换 Keycloak / Entra ID。
          </p>
        </div>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          开发调试可继续使用{" "}
          <Link href="/identity" className="text-accent hover:underline">
            身份选择器
          </Link>
        </p>
      </div>
    </div>
  );
}
