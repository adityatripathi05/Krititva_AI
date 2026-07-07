import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { ProjectNav } from "@/components/project-nav";
import { Badge } from "@/components/ui/badge";
import { serverApi, ServerApiError } from "@/lib/api/server";
import type { Project } from "@/lib/api/types";

export default async function ProjectLayout({
  children,
  params,
}: {
  readonly children: ReactNode;
  readonly params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  let project: Project;
  try {
    project = await serverApi<Project>(`/projects/${projectId}`);
  } catch (err) {
    if (err instanceof ServerApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-3 px-6 pt-6">
        <h1 className="text-xl font-semibold tracking-tight">{project.name}</h1>
        <Badge variant="outline" className="font-mono">
          {project.key}
        </Badge>
        <Badge variant="secondary" className="capitalize">
          {project.methodology}
        </Badge>
      </div>
      <div className="mt-4">
        <ProjectNav projectId={projectId} />
      </div>
      {children}
    </div>
  );
}
