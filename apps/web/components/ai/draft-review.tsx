"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDraftDiff, useProvenance } from "@/lib/hooks/artifacts";
import { diffStats, lineDiff, type DiffRow } from "@/lib/diff";
import { cn } from "@/lib/utils";
import type { Job } from "@/lib/api/types";

import { buildCitationAnchors, CitationText } from "./citations";

type View = "draft" | "diff";

function DraftReader({
  content,
  anchors,
}: {
  readonly content: string;
  readonly anchors: Map<string, string>;
}) {
  return (
    <div className="max-h-[28rem] overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-border bg-background p-4 text-sm leading-relaxed">
      <CitationText text={content} anchors={anchors} />
    </div>
  );
}

const ROW_STYLE: Record<DiffRow["type"], string> = {
  equal: "",
  added: "bg-emerald-500/10",
  removed: "bg-red-500/10",
};

function DiffColumn({
  no,
  text,
  variant,
}: {
  readonly no: number | null;
  readonly text: string | null;
  readonly variant: DiffRow["type"];
}) {
  return (
    <div className={cn("flex gap-2 px-2", text !== null ? ROW_STYLE[variant] : "")}>
      <span className="w-8 shrink-0 select-none text-right text-muted-foreground/60">
        {no ?? ""}
      </span>
      <span className="whitespace-pre-wrap break-words">{text ?? ""}</span>
    </div>
  );
}

function SideBySideDiff({
  before,
  after,
}: {
  readonly before: string;
  readonly after: string;
}) {
  const rows = React.useMemo(() => lineDiff(before, after), [before, after]);
  const stats = React.useMemo(() => diffStats(rows), [rows]);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 text-xs">
        <span className="text-emerald-600 dark:text-emerald-400">+{stats.added} added</span>
        <span className="text-red-600 dark:text-red-400">−{stats.removed} removed</span>
      </div>
      <div className="max-h-[28rem] overflow-auto rounded-md border border-border font-mono text-xs">
        <div className="grid grid-cols-2 divide-x divide-border">
          <div className="sticky top-0 z-10 bg-muted px-2 py-1 font-sans text-[0.7rem] font-medium text-muted-foreground">
            Current approved
          </div>
          <div className="sticky top-0 z-10 bg-muted px-2 py-1 font-sans text-[0.7rem] font-medium text-muted-foreground">
            AI draft
          </div>
          {rows.map((row, i) => (
            <React.Fragment key={i}>
              <DiffColumn no={row.leftNo} text={row.left} variant={row.type} />
              <DiffColumn no={row.rightNo} text={row.right} variant={row.type} />
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

export function DraftReview({
  projectId,
  job,
}: {
  readonly projectId: string;
  readonly job: Job;
}) {
  const [view, setView] = React.useState<View>("draft");
  const { data, isLoading, isError } = useDraftDiff(projectId, job);
  const prov = useProvenance(projectId, job.id);
  const anchors = React.useMemo(
    () => buildCitationAnchors((prov.data ?? []).map((e) => e.section_path)),
    [prov.data],
  );

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading draft…</p>;
  }
  if (isError || data === null || data === undefined) {
    return (
      <p className="text-sm text-muted-foreground">
        The draft document could not be resolved.
      </p>
    );
  }

  const hasBaseline = data.approved !== null;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="inline-flex overflow-hidden rounded-md border border-border">
          <Button
            type="button"
            variant={view === "draft" ? "secondary" : "ghost"}
            size="sm"
            className="rounded-none"
            onClick={() => setView("draft")}
          >
            Draft
          </Button>
          <Button
            type="button"
            variant={view === "diff" ? "secondary" : "ghost"}
            size="sm"
            className="rounded-none"
            onClick={() => setView("diff")}
          >
            Diff
          </Button>
        </div>
        <Badge variant="outline" className="ml-auto">
          v{data.draft.version_no} · draft
        </Badge>
      </div>

      {view === "draft" ? (
        <DraftReader content={data.draft.content_md} anchors={anchors} />
      ) : (
        <SideBySideDiff
          before={data.approved?.content_md ?? ""}
          after={data.draft.content_md}
        />
      )}
      {view === "diff" && !hasBaseline ? (
        <p className="text-xs text-muted-foreground">
          No approved version yet — the whole draft shows as added.
        </p>
      ) : null}
    </div>
  );
}
