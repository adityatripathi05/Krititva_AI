"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAcceptJob, useRejectJob } from "@/lib/hooks/artifacts";
import { ClientApiError } from "@/lib/api/client";
import { toast } from "@/lib/toast";
import type { Job } from "@/lib/api/types";

function errorMessage(err: unknown): string {
  if (err instanceof ClientApiError) return err.code;
  return err instanceof Error ? err.message : "unknown error";
}

export function ReviewActions({
  projectId,
  job,
  canReview,
}: {
  readonly projectId: string;
  readonly job: Job;
  readonly canReview: boolean;
}) {
  const [confirmAccept, setConfirmAccept] = React.useState(false);
  const [rejectOpen, setRejectOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");

  const accept = useAcceptJob(projectId);
  const reject = useRejectJob(projectId);

  if (job.status !== "awaiting_review") return null;

  if (!canReview) {
    return (
      <p className="text-xs text-muted-foreground">
        Only project owners and scrum masters can accept or reject a draft.
      </p>
    );
  }

  async function onAccept() {
    try {
      await accept.mutateAsync(job.id);
      toast("Draft accepted — it is now the canonical version.", "success");
      setConfirmAccept(false);
    } catch (err) {
      toast(`Could not accept: ${errorMessage(err)}`, "error");
    }
  }

  async function onReject() {
    if (reason.trim() === "") return;
    try {
      await reject.mutateAsync({ jobId: job.id, reason: reason.trim() });
      toast("Draft rejected.", "success");
      setReason("");
      setRejectOpen(false);
    } catch (err) {
      toast(`Could not reject: ${errorMessage(err)}`, "error");
    }
  }

  return (
    <div className="flex gap-2">
      <Button size="sm" onClick={() => setConfirmAccept(true)}>
        Accept
      </Button>
      <Button size="sm" variant="outline" onClick={() => setRejectOpen(true)}>
        Reject
      </Button>

      <Dialog open={confirmAccept} onOpenChange={setConfirmAccept}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Accept this draft?</DialogTitle>
            <DialogDescription>
              Accepting promotes the AI draft to the canonical approved version.
              This is recorded in the audit log and cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmAccept(false)}>
              Cancel
            </Button>
            <Button onClick={onAccept} disabled={accept.isPending}>
              {accept.isPending ? "Accepting…" : "Accept draft"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject this draft?</DialogTitle>
            <DialogDescription>
              The draft stays non-canonical. A reason is required and stored on
              the audit trail.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reject-reason">Reason</Label>
            <Textarea
              id="reject-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this draft being rejected?"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={onReject}
              disabled={reject.isPending || reason.trim() === ""}
            >
              {reject.isPending ? "Rejecting…" : "Reject draft"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
