"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { useJobs } from "@/lib/hooks/artifacts";
import { cn } from "@/lib/utils";
import type { Job } from "@/lib/api/types";

import { JobStatusBadge } from "./job-status-badge";

function JobRow({
  job,
  active,
  onSelect,
}: {
  readonly job: Job;
  readonly active: boolean;
  readonly onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full flex-col gap-1 rounded-md border p-2.5 text-left transition-colors",
        active
          ? "border-foreground bg-accent"
          : "border-border hover:bg-accent/50",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium capitalize">
          {job.target_artifact.replace(/_/g, " ")}
        </span>
        <JobStatusBadge status={job.status} />
      </div>
      <span className="text-xs text-muted-foreground">
        {job.agent_role.replace(/_/g, " ")} · {new Date(job.created_at).toLocaleString()}
      </span>
    </button>
  );
}

export function JobList({
  projectId,
  selectedId,
  onSelect,
}: {
  readonly projectId: string;
  readonly selectedId: string | null;
  readonly onSelect: (jobId: string) => void;
}) {
  const { data, isLoading, isError } = useJobs(projectId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </div>
    );
  }
  if (isError) {
    return <p className="text-sm text-destructive">Could not load jobs.</p>;
  }
  const jobs = data ?? [];
  if (jobs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No generation jobs yet. Generate a draft to get started.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {jobs.map((job) => (
        <JobRow
          key={job.id}
          job={job}
          active={job.id === selectedId}
          onSelect={() => onSelect(job.id)}
        />
      ))}
    </div>
  );
}
