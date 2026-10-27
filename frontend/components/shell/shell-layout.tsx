"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  BookOpen,
  Database,
  Gauge,
  Inbox,
  LayoutDashboard,
  MessageSquare,
  MessagesSquare,
  Radio,
  ShieldCheck,
  Ticket as TicketIcon,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useAuthStore } from "@/lib/auth-store";
import { PERMISSIONS, type Permission } from "@/lib/permissions";
import { useAuthorization } from "@/hooks/use-authorization";
import { IdentityPanel } from "./identity-panel";
import { IdentitySwitcher } from "./identity-switcher";
import { ThemeToggle } from "./theme-toggle";

const PORTALS: Array<{ key: string; href: string; label: string }> = [
  { key: "portal", href: "/portal", label: "客户门户" },
  { key: "workspace", href: "/workspace", label: "客服工作台" },
  { key: "admin", href: "/admin", label: "管理控制台" },
];

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  permission?: Permission;
}

const GLOBAL_NAV: NavItem[] = [
  { href: "/chat", label: "对话", icon: MessageSquare, permission: PERMISSIONS.CUSTOMER_CONSULT },
];

const NAV: Record<string, NavItem[]> = {
  portal: [
    { href: "/portal", label: "总览", icon: LayoutDashboard },
    { href: "/portal/consult", label: "提交问题", icon: MessageSquare, permission: PERMISSIONS.CUSTOMER_CONSULT },
    { href: "/portal/tickets", label: "我的工单", icon: TicketIcon, permission: PERMISSIONS.TICKET_READ },
  ],
  workspace: [
    { href: "/workspace", label: "工单队列", icon: Inbox, permission: PERMISSIONS.TICKET_READ },
    { href: "/workspace/approvals", label: "审批", icon: ShieldCheck, permission: PERMISSIONS.APPROVAL_READ },
    { href: "/workspace/knowledge", label: "知识库", icon: BookOpen, permission: PERMISSIONS.KNOWLEDGE_SEARCH },
    { href: "/workspace/consult", label: "咨询调试", icon: Radio, permission: PERMISSIONS.CUSTOMER_CONSULT },
  ],
  admin: [
    { href: "/admin", label: "总览", icon: LayoutDashboard, permission: PERMISSIONS.RUNTIME_READ },
    { href: "/admin/runtime", label: "Runtime", icon: Activity, permission: PERMISSIONS.RUNTIME_READ },
    { href: "/admin/evaluations", label: "评测", icon: Gauge, permission: PERMISSIONS.EVALUATION_READ },
    { href: "/admin/knowledge", label: "知识库管理", icon: Database, permission: PERMISSIONS.KNOWLEDGE_INGEST },
    { href: "/admin/activity", label: "会话活动", icon: MessagesSquare, permission: PERMISSIONS.CONVERSATION_READ },
  ],
};

export function ShellLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const identity = useAuthStore((state) => state.identity);
  const { can, isLoading: authzLoading, error: authzError } = useAuthorization();
  // SSR always renders the loader (no localStorage), so gate the real shell
  // behind client mount to avoid hydration mismatch. A missing identity is
  // then shown as an inline picker instead of navigating — router.replace
  // inside a layout is unreliable in the App Router and caused a stuck
  // "确认身份" screen.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        正在确认身份…
      </div>
    );
  }

  if (!identity) {
    return <IdentityPanel />;
  }

  const segment = pathname.split("/")[1] ?? "chat";
  const portalKey = PORTALS.some((p) => p.key === segment) ? segment : "portal";
  const navItems = NAV[portalKey] ?? NAV.portal;
  const isChat = pathname.startsWith("/chat");

  const isActive = (href: string) =>
    href === "/" ? pathname === href : pathname === href || pathname.startsWith(href + "/");

  const canSee = (item: NavItem) =>
    !item.permission || (!authzLoading && !authzError && can(item.permission));

  const canSeeWorkspace = !authzLoading && !authzError && [
    PERMISSIONS.TICKET_READ,
    PERMISSIONS.APPROVAL_READ,
    PERMISSIONS.KNOWLEDGE_SEARCH,
    PERMISSIONS.CUSTOMER_CONSULT,
  ].some(can);
  const canSeeAdmin = !authzLoading && !authzError && [
    PERMISSIONS.RUNTIME_READ,
    PERMISSIONS.EVALUATION_READ,
    PERMISSIONS.KNOWLEDGE_INGEST,
  ].some(can);

  const portalHref = (portal: (typeof PORTALS)[number]) => {
    if (portal.key === "workspace" && !can(PERMISSIONS.TICKET_READ)) {
      if (can(PERMISSIONS.APPROVAL_READ)) return "/workspace/approvals";
      if (can(PERMISSIONS.KNOWLEDGE_SEARCH)) return "/workspace/knowledge";
      return "/workspace/consult";
    }
    if (portal.key === "admin" && !can(PERMISSIONS.RUNTIME_READ)) {
      return can(PERMISSIONS.EVALUATION_READ) ? "/admin/evaluations" : "/admin/knowledge";
    }
    return portal.href;
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card">
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-[11px] font-semibold text-accent-foreground">
            CD
          </span>
          <div className="leading-tight">
            <p className="text-sm font-semibold tracking-tight">CloudDesk</p>
            <p className="text-[11px] text-muted-foreground">客户运营平台</p>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-auto p-2">
          {[...GLOBAL_NAV, ...navItems].filter(canSee).map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border p-3 text-xs text-muted-foreground">
          <p className="truncate font-medium text-foreground">{identity.tenantSlug}</p>
          <p className="truncate">{identity.userName}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-4 border-b border-border px-4">
          <div className="flex gap-1">
            {PORTALS.filter((portal) =>
              portal.key === "portal" ||
              (portal.key === "workspace" && canSeeWorkspace) ||
              (portal.key === "admin" && canSeeAdmin),
            ).map((portal) => {
              const active = portalKey === portal.key;
              return (
                <Link
                  key={portal.key}
                  href={portalHref(portal)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {portal.label}
                </Link>
              );
            })}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <IdentitySwitcher />
          </div>
        </header>
        <main className={cn("flex-1", isChat ? "overflow-hidden" : "overflow-auto p-6")}>
          {children}
        </main>
      </div>
    </div>
  );
}
