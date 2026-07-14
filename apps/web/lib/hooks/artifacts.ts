"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { clientApi } from "@/lib/api/client";
import {
  isLiveStatus,
  type AcceptResult,
  type DocumentSummary,
  type DocumentVersion,
  type EnqueuedJob,
  type GenerateArtifactRequest,
  type Job,
  type ProgressFrame,
  type ProvenanceEntry,
} from "@/lib/api/types";

export const jobsKey = (projectId: string) => ["ai-jobs", projectId] as const;
export const jobKey = (projectId: string, jobId: string) =>
  ["ai-job", projectId, jobId] as const;
export const provenanceKey = (projectId: string, jobId: string) =>
  ["ai-provenance", projectId, jobId] as const;

export function useJobs(projectId: string) {
  return useQuery({
    queryKey: jobsKey(projectId),
    queryFn: () => clientApi<Job[]>(`/projects/${projectId}/artifacts/jobs`),
  });
}

export function useProvenance(projectId: string, jobId: string | null) {
  return useQuery({
    queryKey: provenanceKey(projectId, jobId ?? "none"),
    enabled: jobId !== null,
    queryFn: () =>
      clientApi<ProvenanceEntry[]>(
        `/projects/${projectId}/artifacts/jobs/${jobId}/provenance`,
      ),
  });
}

export function useEnqueueArtifact(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GenerateArtifactRequest) =>
      clientApi<EnqueuedJob>(`/projects/${projectId}/artifacts`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: jobsKey(projectId) }),
  });
}

export function useAcceptJob(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) =>
      clientApi<AcceptResult>(
        `/projects/${projectId}/artifacts/jobs/${jobId}/accept`,
        { method: "POST" },
      ),
    onSuccess: (_res, jobId) => {
      qc.invalidateQueries({ queryKey: jobsKey(projectId) });
      qc.invalidateQueries({ queryKey: jobKey(projectId, jobId) });
    },
  });
}

interface RejectArgs {
  jobId: string;
  reason: string;
}

export function useRejectJob(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, reason }: RejectArgs) =>
      clientApi<void>(`/projects/${projectId}/artifacts/jobs/${jobId}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),
    onSuccess: (_res, { jobId }) => {
      qc.invalidateQueries({ queryKey: jobsKey(projectId) });
      qc.invalidateQueries({ queryKey: jobKey(projectId, jobId) });
    },
  });
}

export interface JobStream {
  readonly job: Job | undefined;
  readonly frames: readonly ProgressFrame[];
  readonly connected: boolean;
}

/**
 * Live job status via SSE, with a polling fallback. The single job status query
 * is the source of truth; the EventSource pushes `state`/`progress` frames into
 * its cache and triggers a provenance refetch on the terminal frame. EventSource
 * auto-reconnects on transient drops; while the stream is down (or never opened)
 * the query polls every 4 s so status is never stranded. Neither runs once the
 * job leaves the live states (`queued`/`running`).
 */
export function useJobStream(
  projectId: string,
  jobId: string,
  initialJob?: Job,
): JobStream {
  const qc = useQueryClient();
  const connectedRef = React.useRef(false);
  const [connected, setConnected] = React.useState(false);
  const [frames, setFrames] = React.useState<ProgressFrame[]>([]);

  const query = useQuery({
    queryKey: jobKey(projectId, jobId),
    queryFn: () =>
      clientApi<Job>(`/projects/${projectId}/artifacts/jobs/${jobId}`),
    initialData: initialJob,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (status === undefined || !isLiveStatus(status)) return false;
      // Poll fast as an SSE fallback while disconnected; keep a slow reconcile
      // poll even when connected so a missed terminal frame (subscribe race)
      // can't strand the UI in "running" forever.
      return connectedRef.current ? 15000 : 4000;
    },
  });

  const status = query.data?.status;
  const live = status !== undefined && isLiveStatus(status);

  React.useEffect(() => {
    if (!live) return;
    const url = `/api/v1/projects/${projectId}/artifacts/jobs/${jobId}/events`;
    const es = new EventSource(url, { withCredentials: true });
    const mark = (up: boolean) => {
      connectedRef.current = up;
      setConnected(up);
    };
    const onState = (e: MessageEvent<string>) => {
      const snapshot = JSON.parse(e.data) as Job;
      qc.setQueryData(jobKey(projectId, jobId), snapshot);
    };
    const onProgress = (e: MessageEvent<string>) => {
      const frame = JSON.parse(e.data) as ProgressFrame;
      setFrames((prev) => [...prev, frame]);
      if (frame.step === "done" || frame.step === "failed") {
        void qc.invalidateQueries({ queryKey: jobKey(projectId, jobId) });
        void qc.invalidateQueries({ queryKey: jobsKey(projectId) });
        void qc.invalidateQueries({ queryKey: provenanceKey(projectId, jobId) });
        es.close();
        mark(false);
      }
    };
    es.addEventListener("open", () => mark(true));
    es.addEventListener("state", onState as EventListener);
    es.addEventListener("progress", onProgress as EventListener);
    es.addEventListener("heartbeat", () => mark(true));
    es.onerror = () => mark(false); // EventSource retries; the poll fallback covers the gap.
    return () => {
      es.close();
      connectedRef.current = false;
    };
  }, [live, projectId, jobId, qc]);

  return { job: query.data, frames, connected };
}

export interface DraftDiff {
  readonly doc: DocumentSummary;
  readonly draft: DocumentVersion;
  readonly approved: DocumentVersion | null;
}

const DOC_ARTIFACTS = new Set(["srs", "hld", "lld", "test_plan"]);

/**
 * Resolve the draft version a document-producing job created plus the current
 * approved version, for the side-by-side diff. Work-item artifacts (test_cases,
 * *_breakdown) have no document version, so the query stays disabled.
 */
export function useDraftDiff(projectId: string, job: Job | undefined) {
  const versionId = job?.result_document_version ?? null;
  return useQuery({
    queryKey: ["ai-draft-diff", projectId, job?.id, versionId],
    enabled:
      job !== undefined &&
      versionId !== null &&
      DOC_ARTIFACTS.has(job.target_artifact),
    queryFn: async (): Promise<DraftDiff | null> => {
      const docs = await clientApi<DocumentSummary[]>(
        `/projects/${projectId}/documents`,
      );
      const candidates = docs.filter((d) => d.doc_type === job!.target_artifact);
      for (const doc of candidates) {
        const versions = await clientApi<DocumentVersion[]>(
          `/projects/${projectId}/documents/${doc.id}/versions`,
        );
        const draft = versions.find((v) => v.id === versionId);
        if (draft === undefined) continue;
        const approved =
          versions.find(
            (v) => v.id === doc.current_version_id && v.status === "approved",
          ) ?? null;
        return { doc, draft, approved };
      }
      return null;
    },
  });
}
