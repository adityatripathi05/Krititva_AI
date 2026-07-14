"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

// The Architect/QA prompts mandate citations in the form `[SRS §4.6.5]` /
// `[HLD §3.2]` (LLD §5.5). We linkify those tokens in the draft body to the
// matching provenance row, which is anchored by the same section path.
const CITATION_RE = /\[(SRS|HLD|LLD)\s*§?\s*([0-9]+(?:\.[0-9]+)*)\]/gi;

export interface Citation {
  readonly raw: string;
  readonly source: string;
  readonly section: string;
}

/** DOM id for the provenance row a `§section` citation deep-links to. */
export function provenanceAnchorId(section: string): string {
  return `prov-${section}`;
}

export function parseCitations(text: string): Citation[] {
  const out: Citation[] = [];
  for (const m of text.matchAll(CITATION_RE)) {
    const source = m[1];
    const section = m[2];
    if (source === undefined || section === undefined) continue;
    out.push({ raw: m[0], source: source.toUpperCase(), section });
  }
  return out;
}

export function CitationChip({
  source,
  section,
  className,
}: {
  readonly source: string;
  readonly section: string;
  readonly className?: string;
}) {
  return (
    <a
      href={`#${provenanceAnchorId(section)}`}
      className={cn(
        "inline-flex items-center rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.7rem] font-medium text-muted-foreground no-underline transition-colors hover:border-foreground hover:text-foreground",
        className,
      )}
      title={`Jump to the ${source} §${section} source in provenance`}
    >
      {source} §{section}
    </a>
  );
}

/** Render text with any `[SRC §x.y.z]` citations replaced by deep-link chips. */
export function CitationText({ text }: { readonly text: string }) {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(CITATION_RE)) {
    const source = m[1];
    const section = m[2];
    if (source === undefined || section === undefined) continue;
    const start = m.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    nodes.push(
      <CitationChip key={key++} source={source.toUpperCase()} section={section} />,
    );
    last = start + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes}</>;
}
