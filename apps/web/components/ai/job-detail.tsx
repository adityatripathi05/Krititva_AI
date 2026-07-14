"use client";

import { Loader2, Wifi, WifiOff } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { useJobStream } from "@/lib/hooks/artifacts";
import { isReviewerRole, useProjectRole } from "@/lib/hooks/me";
import { isLiveStatus, type Job } from "@/lib/api/types";

import { DraftReview } from "./draft-review";
import { JobStatusBadge } from "./job-status-badge";
import { ProvenanceList } from "./provenance-list";
import { ReviewActions } from "./review-actions";

function Section({
  title,
  children,
}: {
  readonly title: string;
  readonly children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}

function LiveProgress({ connected }: { readonly connected: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm">
      <Loader2 className="size-4 animate-spin text-muted-foreground" />
      <span>Generating draft…</span>
      <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground">
        {connected ? (
          <>
            <Wifi className="size-3.5" /> live
          </>
        ) : (
          <>
            <WifiOff className="size-3.5" /> reconnecting
          </>
        )}
      </span>
    </div>
  );
}

export function JobDetail({
  projectId,
  jobId,
  initialJob,
}: {
  readonly projectId: string;
  readonly jobId: string;
  readonly initialJob?: Job;
}) {
  const { job, connected } = useJobStream(projectId, jobId, initialJob);
  const role = useProjectRole(projectId);
  const canReview = isReviewerRole(role);

  if (job === undefined) {
    return <p className="text-sm text-muted-foreground">Loading job…</p>;
  }

  const live = isLiveStatus(job.status);
  const hasDocument = job.result_document_version !== null;

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold capitalize">
            {job.target_artifact.replace(/_/g, " ")}
          </h2>
          <JobStatusBadge status={job.status} />
          <Badge variant="outline" className="capitalize">
            {job.agent_role.replace(/_/g, " ")}
          </Badge>
        </div>
        {job.model_used !== null ? (
          <p className="text-xs text-muted-foreground">
            {job.model_used}
            {job.output_tokens !== null ? ` · ${job.output_tokens} output tokens` : ""}
          </p>
        ) : null}
      </div>

      {live ? <LiveProgress connected={connected} /> : null}

      {job.status === "failed" ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <p className="font-medium text-destructive">Generation failed</p>
          {job.error !== null ? (
            <p className="mt-1 text-muted-foreground">{job.error}</p>
          ) : null}
        </div>
      ) : null}

      {!live && job.status !== "failed" ? (
        <>
          {hasDocument ? (
            <Section title="Draft">
              <DraftReview projectId={projectId} job={job} />
            </Section>
          ) : (
            <Section title="Draft">
              <p className="text-sm text-muted-foreground">
                This agent produced work items rather than a document. Review them
                on the{" "}
                <Link href={`/projects/${projectId}/backlog`} className="underline">
                  backlog
                </Link>
                .
              </p>
            </Section>
          )}

          <Section title="Provenance">
            <ProvenanceList projectId={projectId} jobId={jobId} />
          </Section>

          <ReviewActions projectId={projectId} job={job} canReview={canReview} />
        </>
      ) : null}
    </div>
  );
}
