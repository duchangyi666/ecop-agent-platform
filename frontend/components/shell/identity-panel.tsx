"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, UserPlus } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { AuthSessionResponse, LoginRequest, RegisterRequest } from "@/lib/types";
import { useAuthStore } from "@/lib/auth-store";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { cn } from "@/lib/cn";

type Mode = "login" | "register";

/** Login / register gate. On success stores the JWT session and enters the shell. */
export function IdentityPanel() {
  const router = useRouter();
  const setIdentity = useAuthStore((state) => state.setIdentity);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const signInWithSession = (session: AuthSessionResponse) => {
    setIdentity({
      tenantId: session.tenant_id,
      tenantSlug: session.tenant_slug,
      userId: session.user_id,
      userName: session.display_name,
      actorType: session.actor_type,
      accessToken: session.access_token,
    });
    router.push("/chat");
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        const body: LoginRequest = { email, password };
        if (tenantSlug.trim()) body.tenant_slug = tenantSlug.trim().toLowerCase();
        const session = await api.post<AuthSessionResponse>("/api/v1/auth/login", body);
        signInWithSession(session);
      } else {
        const body: RegisterRequest = {
          email,
          display_name: displayName.trim(),
          password,
        };
        if (tenantSlug.trim()) body.tenant_slug = tenantSlug.trim().toLowerCase();
        const session = await api.post<AuthSessionResponse>("/api/v1/auth/register", body);
        signInWithSession(session);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-foreground">
          CD
        </span>
        <div>
          <h1 className="text-lg font-semibold">CloudDesk 企业客户运营平台</h1>
          <p className="text-xs text-muted-foreground">登录或注册后进入对应工作台</p>
        </div>
      </div>

      <div className="w-full max-w-md rounded-lg border border-border bg-card shadow-sm">
        <div className="grid grid-cols-2 border-b border-border">
          {(["login", "register"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => switchMode(tab)}
              className={cn(
                "flex items-center justify-center gap-1.5 py-3 text-sm font-medium transition-colors",
                mode === tab
                  ? "border-b-2 border-accent text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {tab === "login" ? (
                <LogIn className="h-3.5 w-3.5" />
              ) : (
                <UserPlus className="h-3.5 w-3.5" />
              )}
              {tab === "login" ? "登录" : "注册"}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-5">
          {mode === "register" && (
            <Field label="显示名称">
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="例如：张小明"
                maxLength={200}
                required
              />
            </Field>
          )}
          <Field label="邮箱">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              maxLength={255}
              autoComplete="email"
              required
            />
          </Field>
          <Field label="密码">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "至少 8 位" : "请输入密码"}
              minLength={mode === "register" ? 8 : 1}
              maxLength={128}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              required
            />
          </Field>
          <Field label="租户标识（可选）">
            <Input
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value)}
              placeholder={mode === "login" ? "不填则匹配第一个匹配的租户" : "留空自动创建（按邮箱前缀）"}
              maxLength={63}
            />
          </Field>

          {error && (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
              {error}
            </p>
          )}

          <Button type="submit" loading={submitting} size="lg" className="mt-1">
            {mode === "login" ? "登录" : "注册并进入"}
          </Button>
        </form>
      </div>

      <p className="max-w-md text-center text-xs text-muted-foreground">
        登录后使用 JWT Bearer 认证；本地开发环境也可使用请求头边界（X-Tenant-Id / X-Actor-Id / X-Actor-Type）。
      </p>
    </div>
  );
}
