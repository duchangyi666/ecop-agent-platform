import type { ReactNode } from "react";
import { ShellLayout } from "@/components/shell/shell-layout";

export default function Layout({ children }: { children: ReactNode }) {
  return <ShellLayout>{children}</ShellLayout>;
}
