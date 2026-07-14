"use client";

import { Sparkles } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { invocableArtifacts, type GeneratableArtifact } from "@/lib/ai-catalog";
import { useEnqueueArtifact } from "@/lib/hooks/artifacts";
import { useProjectRole } from "@/lib/hooks/me";
import { useWorkItems } from "@/lib/hooks/work-items";
import { ClientApiError } from "@/lib/api/client";
import { toast } from "@/lib/toast";

const NO_STORY = "__none__";

function artifactKey(g: GeneratableArtifact): string {
  return `${g.agent}:${g.artifact}`;
}

export function GenerateForm({
  projectId,
  onEnqueued,
}: {
  readonly projectId: string;
  readonly onEnqueued: (jobId: string) => void;
}) {
  const role = useProjectRole(projectId);
  const options = invocableArtifacts(role);
  const [selected, setSelected] = React.useState<string>("");
  const [storyId, setStoryId] = React.useState<string>(NO_STORY);
  const [instructions, setInstructions] = React.useState("");

  const enqueue = useEnqueueArtifact(projectId);
  const items = useWorkItems(projectId);
  const stories = (items.data ?? []).filter((w) => w.kind === "story");

  const chosen = options.find((g) => artifactKey(g) === selected) ?? null;
  const needsStory = chosen?.needsFocusStory === true;
  const focusMissing = needsStory && storyId === NO_STORY;

  if (options.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Your project role cannot invoke any AI agent.
      </p>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (chosen === null || focusMissing) return;
    try {
      const res = await enqueue.mutateAsync({
        agent_role: chosen.agent,
        target_artifact: chosen.artifact,
        focus_item_id: needsStory ? storyId : null,
        instructions: instructions.trim() === "" ? null : instructions.trim(),
      });
      toast(`Generation queued (${chosen.label}).`, "success");
      setInstructions("");
      onEnqueued(res.job_id);
    } catch (err) {
      const code = err instanceof ClientApiError ? err.code : "error";
      toast(`Could not queue generation: ${code}`, "error");
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label>Artifact</Label>
        <Select value={selected} onValueChange={setSelected}>
          <SelectTrigger>
            <SelectValue placeholder="Choose what to generate" />
          </SelectTrigger>
          <SelectContent>
            {options.map((g) => (
              <SelectItem key={artifactKey(g)} value={artifactKey(g)}>
                {g.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {needsStory ? (
        <div className="space-y-2">
          <Label>Focus story</Label>
          <Select value={storyId} onValueChange={setStoryId}>
            <SelectTrigger>
              <SelectValue placeholder="Select a story" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_STORY}>Select a story</SelectItem>
              {stories.map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.key} · {s.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {stories.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No stories exist yet to generate test cases for.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-2">
        <Label htmlFor="ai-instructions">Instructions (optional)</Label>
        <Textarea
          id="ai-instructions"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="Focus, constraints, or emphasis for this generation."
          maxLength={4000}
        />
      </div>

      <Button
        type="submit"
        disabled={chosen === null || focusMissing || enqueue.isPending}
      >
        <Sparkles />
        {enqueue.isPending ? "Queuing…" : "Generate draft"}
      </Button>
    </form>
  );
}
