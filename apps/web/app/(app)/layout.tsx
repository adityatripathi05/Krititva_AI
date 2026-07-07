import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { LogoutButton } from "@/components/logout-button";
import { serverApi, ServerApiError } from "@/lib/api/server";
import type { CurrentUser } from "@/lib/api/types";

export default async function AppLayout({ children }: { readonly children: ReactNode }) {
  let me: CurrentUser;
  try {
    me = await serverApi<CurrentUser>("/auth/me");
  } catch (err) {
    if (err instanceof ServerApiError && (err.status === 401 || err.status === 403)) {
      redirect("/login");
    }
    throw err;
  }

  return (
    <div className="grid min-h-screen grid-cols-[240px_1fr]">
      <aside className="flex flex-col border-r border-border bg-card">
        <div className="flex h-14 items-center border-b border-border px-4">
          <Link href="/dashboard" className="font-semibold tracking-tight">
            Krititva AI
          </Link>
        </div>
        <AppSidebar />
      </aside>
      <div className="flex flex-col">
        <header className="flex h-14 items-center justify-between border-b border-border px-6">
          <div className="text-sm text-muted-foreground">
            {me.user.display_name}
            <span className="mx-2">·</span>
            <span className="capitalize">{me.user.org_role.replace("_", " ")}</span>
          </div>
          <LogoutButton />
        </header>
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
