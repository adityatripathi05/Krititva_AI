import { Badge, type BadgeVariant } from "@/components/ui/badge";
import type { JobStatus } from "@/lib/api/types";

const STATUS: Record<JobStatus, { label: string; variant: BadgeVariant }> = {
  queued: { label: "Queued", variant: "outline" },
  running: { label: "Running", variant: "secondary" },
  awaiting_review: { label: "Awaiting review", variant: "default" },
  accepted: { label: "Accepted", variant: "default" },
  rejected: { label: "Rejected", variant: "destructive" },
  failed: { label: "Failed", variant: "destructive" },
};

export function JobStatusBadge({ status }: { readonly status: JobStatus }) {
  const s = STATUS[status];
  return <Badge variant={s.variant}>{s.label}</Badge>;
}
