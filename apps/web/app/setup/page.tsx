import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { SetupForm } from "@/components/setup-form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { isBootstrapped } from "@/lib/api/bootstrap";

export const metadata: Metadata = { title: "First-run setup" };

export default async function SetupPage() {
  if (await isBootstrapped()) {
    redirect("/login");
  }
  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-12">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Welcome to Krititva AI</CardTitle>
          <CardDescription>
            Create your organization and the first admin account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SetupForm />
        </CardContent>
      </Card>
    </main>
  );
}
