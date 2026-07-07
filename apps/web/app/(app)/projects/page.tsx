import type { Metadata } from "next";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { serverApi } from "@/lib/api/server";
import type { Project } from "@/lib/api/types";

export const metadata: Metadata = { title: "Projects" };

export default async function ProjectsPage() {
  const projects = await serverApi<Project[]>("/projects");

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
      {projects.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No projects visible to you yet.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Link key={p.id} href={`/projects/${p.id}`}>
              <Card className="h-full transition-colors hover:border-foreground/20">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle className="text-base">{p.name}</CardTitle>
                    <Badge variant="outline" className="shrink-0 font-mono">
                      {p.key}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-1 text-sm text-muted-foreground">
                  <p className="capitalize">{p.methodology}</p>
                  <p className="capitalize">{p.status.replace("_", " ")}</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
