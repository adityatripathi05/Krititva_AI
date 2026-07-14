"use client";

import { Badge } from "@/components/ui/badge";
import { useProvenance } from "@/lib/hooks/artifacts";
import type { ProvenanceEntry, ProvenanceStage } from "@/lib/api/types";

import { provenanceAnchorId } from "./citations";

const STAGE_LABEL: Record<ProvenanceStage, string> = {
  lineage: "Lineage",
  semantic: "Semantic",
  operational: "Operational",
};

function ProvenanceRow({ entry }: { readonly entry: ProvenanceEntry }) {
  const section = entry.section_path;
  return (
    <li
      id={section ? provenanceAnchorId(section) : undefined}
      className="scroll-mt-24 rounded-md border border-border p-2.5 target:border-foreground target:bg-accent"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{STAGE_LABEL[entry.stage]}</Badge>
        {section ? (
          <span className="font-mono text-xs font-medium">§{section}</span>
        ) : (
          <span className="text-xs text-muted-foreground">no section</span>
        )}
        {entry.similarity !== null ? (
          <span className="ml-auto text-xs text-muted-foreground">
            {Math.round(entry.similarity * 100)}% match
          </span>
        ) : null}
      </div>
      {entry.chunk_hash ? (
        <p className="mt-1 truncate font-mono text-[0.7rem] text-muted-foreground">
          chunk {entry.chunk_hash.slice(0, 12)}…
        </p>
      ) : null}
    </li>
  );
}

export function ProvenanceList({
  projectId,
  jobId,
}: {
  readonly projectId: string;
  readonly jobId: string;
}) {
  const { data, isLoading, isError } = useProvenance(projectId, jobId);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading provenance…</p>;
  }
  if (isError) {
    return <p className="text-sm text-destructive">Could not load provenance.</p>;
  }
  const entries = data ?? [];
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No provenance recorded for this draft.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {entries.map((e) => (
        <ProvenanceRow key={e.id} entry={e} />
      ))}
    </ul>
  );
}
