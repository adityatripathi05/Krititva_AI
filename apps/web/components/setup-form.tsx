"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SetupForm() {
  const router = useRouter();
  const [form, setForm] = React.useState({
    org_name: "",
    display_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { code?: string } | null;
        setError(
          body?.code === "already_bootstrapped"
            ? "This workspace is already set up. Redirecting to sign-in…"
            : "Setup failed. Check the details and try again.",
        );
        if (body?.code === "already_bootstrapped") {
          setTimeout(() => router.replace("/login"), 1200);
        }
        return;
      }
      router.replace("/dashboard");
      router.refresh();
    } catch {
      setError("Could not reach the server.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="org_name">Organization name</Label>
        <Input
          id="org_name"
          required
          value={form.org_name}
          onChange={(e) => set("org_name", e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="display_name">Your name</Label>
        <Input
          id="display_name"
          required
          value={form.display_name}
          onChange={(e) => set("display_name", e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={form.email}
          onChange={(e) => set("email", e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          minLength={8}
          required
          value={form.password}
          onChange={(e) => set("password", e.target.value)}
        />
        <p className="text-xs text-muted-foreground">At least 8 characters.</p>
      </div>
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "Creating workspace…" : "Create workspace"}
      </Button>
    </form>
  );
}
