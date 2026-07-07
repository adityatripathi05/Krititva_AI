import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/login-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { isBootstrapped } from "@/lib/api/bootstrap";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  readonly searchParams: Promise<{ next?: string }>;
}) {
  if (!(await isBootstrapped())) {
    redirect("/setup");
  }
  const { next } = await searchParams;
  // Only accept a same-origin absolute path. Reject protocol-relative (`//host`)
  // and backslash (`/\host`) forms, which browsers normalize to another origin.
  const isSafe =
    !!next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\");
  const target = isSafe ? next : "/dashboard";
  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-12">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Krititva AI</CardTitle>
          <CardDescription>Sign in to your workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm next={target} />
        </CardContent>
      </Card>
    </main>
  );
}
