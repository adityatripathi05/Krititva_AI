"use client";

import { useQuery } from "@tanstack/react-query";

import { clientApi } from "@/lib/api/client";
import type { CurrentUser, ProjectRole } from "@/lib/api/types";

const REVIEWER_ROLES: ReadonlySet<ProjectRole> = new Set<ProjectRole>([
  "project_owner",
  "scrum_master",
]);

export function useCurrentUser() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => clientApi<CurrentUser>("/auth/me"),
    staleTime: 5 * 60_000,
  });
}

/** The caller's role in a project, or `null` if they have no membership. */
export function useProjectRole(projectId: string): ProjectRole | null {
  const { data } = useCurrentUser();
  return (
    data?.memberships.find((m) => m.project_id === projectId)?.role ?? null
  );
}

export function isReviewerRole(role: ProjectRole | null): boolean {
  return role !== null && REVIEWER_ROLES.has(role);
}
