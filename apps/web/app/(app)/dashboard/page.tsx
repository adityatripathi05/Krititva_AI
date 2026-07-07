import type { Metadata } from "next";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { serverApi } from "@/lib/api/server";
import type { Project } from "@/lib/api/types";

export const metadata: Metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const projects = await serverApi<Project[]>("/projects");
  const active = projects.filter((p) => p.status === "active").length;

  return (
    <div className="mx-auto max-w-5xl space-y-8 px-6 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Projects
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{projects.length}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Active
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{active}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Methodologies
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {new Set(projects.map((p) => p.methodology)).size}
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Recent projects</h2>
          <Link href="/projects" className="text-sm text-muted-foreground hover:underline">
            View all
          </Link>
        </div>
        {projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No projects yet. An org admin can create one from the Projects page.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {projects.slice(0, 6).map((p) => (
              <Link key={p.id} href={`/projects/${p.id}`}>
                <Card className="transition-colors hover:border-foreground/20">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">{p.name}</CardTitle>
                      <Badge variant="outline" className="font-mono">
                        {p.key}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="text-sm capitalize text-muted-foreground">
                    {p.methodology} · {p.status.replace("_", " ")}
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
