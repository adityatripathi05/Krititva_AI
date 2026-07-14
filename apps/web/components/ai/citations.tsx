"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

// The Architect/QA prompts mandate citations in the form `[SRS §4.6.5]` /
// `[HLD §3.2]` (LLD §5.5). We linkify those tokens in the draft body to the
// matching provenance row. Provenance `section_path` is a heading *breadcrumb*
// (e.g. "4.6 AI Layer / 4.6.5 Draft Review"), not a bare number, so we key the
// link on the numeric section tokens found inside that breadcrumb.
const CITATION_RE = /\[(SRS|HLD|LLD)\s*§?\s*([0-9]+(?:\.[0-9]+)*)\]/gi;
const NUMERIC_RE = /[0-9]+(?:\.[0-9]+)*/g;

export interface Citation {
  readonly raw: string;
  readonly source: string;
  readonly section: string;
}

export function slugifySection(path: string): string {
  const slug = path
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug === "" ? "unknown" : slug;
}

/** DOM id for the provenance row a citation deep-links to. */
export function provenanceAnchorId(sectionPath: string): string {
  return `prov-${slugifySection(sectionPath)}`;
}

/**
 * Map each numeric section token appearing in the provenance breadcrumbs to the
 * DOM anchor of the row it belongs to, so a citation like `4.6.5` resolves to
 * the provenance entry whose `section_path` contains `4.6.5`.
 */
export function buildCitationAnchors(
  sectionPaths: readonly (string | null)[],
): Map<string, string> {
  const anchors = new Map<string, string>();
  for (const path of sectionPaths) {
    if (path === null) continue;
    const id = provenanceAnchorId(path);
    for (const m of path.matchAll(NUMERIC_RE)) anchors.set(m[0], id);
  }
  return anchors;
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

const CHIP_BASE =
  "inline-flex items-center rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.7rem] font-medium text-muted-foreground";

function CitationChip({
  source,
  section,
  anchorId,
}: {
  readonly source: string;
  readonly section: string;
  readonly anchorId: string | undefined;
}) {
  const label = `${source} §${section}`;
  if (anchorId === undefined) {
    // No provenance row cites this section — render an inert chip rather than a
    // dead link so the citation is still visible.
    return (
      <span className={CHIP_BASE} title="No matching provenance source">
        {label}
      </span>
    );
  }
  return (
    <a
      href={`#${anchorId}`}
      className={cn(
        CHIP_BASE,
        "no-underline transition-colors hover:border-foreground hover:text-foreground",
      )}
      title={`Jump to the ${label} source in provenance`}
    >
      {label}
    </a>
  );
}

/** Render text with `[SRC §x.y.z]` citations replaced by chips; chips deep-link
 * when a provenance anchor for that section exists in `anchors`. */
export function CitationText({
  text,
  anchors,
}: {
  readonly text: string;
  readonly anchors?: Map<string, string>;
}) {
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
      <CitationChip
        key={key++}
        source={source.toUpperCase()}
        section={section}
        anchorId={anchors?.get(section)}
      />,
    );
    last = start + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes}</>;
}
