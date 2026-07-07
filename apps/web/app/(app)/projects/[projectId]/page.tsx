import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { serverApi } from "@/lib/api/server";
import { categoryBadgeVariant } from "@/lib/api/types";
import type { Project, WorkflowState, WorkItem } from "@/lib/api/types";

export default async function ProjectHomePage({
  params,
}: {
  readonly params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const [project, states, items] = await Promise.all([
    serverApi<Project>(`/projects/${projectId}`),
    serverApi<WorkflowState[]>(`/projects/${projectId}/workflow/states`),
    serverApi<WorkItem[]>(`/projects/${projectId}/work_items`),
  ]);

  const countByState = new Map<string, number>();
  for (const item of items) {
    countByState.set(item.state_id, (countByState.get(item.state_id) ?? 0) + 1);
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 px-6 py-8">
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Work items
            </CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">{items.length}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Status
            </CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-medium capitalize">
            {project.status.replace("_", " ")}
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Workflow</h2>
          <Link
            href={`/projects/${projectId}/board`}
            className="text-sm text-muted-foreground hover:underline"
          >
            Open board
          </Link>
        </div>
        <div className="flex flex-wrap gap-2">
          {states.map((s) => (
            <Badge key={s.id} variant={categoryBadgeVariant(s.category)}>
              {s.label} · {countByState.get(s.id) ?? 0}
            </Badge>
          ))}
        </div>
      </section>
    </div>
  );
}
