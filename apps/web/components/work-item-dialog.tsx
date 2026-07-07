"use client";

import { Plus } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "@/lib/toast";
import {
  useCreateWorkItem,
  useHierarchyRules,
  useWorkItems,
} from "@/lib/hooks/work-items";
import type { WorkItemKind } from "@/lib/api/types";

const KINDS: readonly WorkItemKind[] = [
  "phase",
  "epic",
  "feature",
  "story",
  "task",
  "bug",
  "deliverable",
  "test_case",
];

const NO_PARENT = "__none__";

export function WorkItemDialog({ projectId }: { readonly projectId: string }) {
  const [open, setOpen] = React.useState(false);
  const [kind, setKind] = React.useState<WorkItemKind>("story");
  const [title, setTitle] = React.useState("");
  const [parentId, setParentId] = React.useState<string>(NO_PARENT);

  const rules = useHierarchyRules(projectId);
  const items = useWorkItems(projectId);
  const create = useCreateWorkItem(projectId);

  // Hierarchy-aware: only items whose kind may parent the chosen kind qualify.
  const allowedParentKinds = new Set(
    (rules.data ?? []).filter((r) => r.child_kind === kind).map((r) => r.parent_kind),
  );
  const parentOptions = (items.data ?? []).filter((w) => allowedParentKinds.has(w.kind));

  React.useEffect(() => {
    // Reset the parent when the chosen kind can no longer live under it.
    if (parentId !== NO_PARENT && !parentOptions.some((p) => p.id === parentId)) {
      setParentId(NO_PARENT);
    }
  }, [parentId, parentOptions]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await create.mutateAsync({
        kind,
        title,
        parent_id: parentId === NO_PARENT ? null : parentId,
      });
      toast(`Created ${kind}.`, "success");
      setTitle("");
      setParentId(NO_PARENT);
      setOpen(false);
    } catch (err) {
      toast(
        `Could not create item${err instanceof Error && err.message ? `: ${err.message}` : ""}`,
        "error",
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus />
          New item
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New work item</DialogTitle>
          <DialogDescription>
            The parent list is filtered to kinds this methodology allows.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="wi-title">Title</Label>
            <Input
              id="wi-title"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Kind</Label>
            <Select value={kind} onValueChange={(v) => setKind(v as WorkItemKind)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((k) => (
                  <SelectItem key={k} value={k} className="capitalize">
                    {k.replace("_", " ")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Parent</Label>
            <Select value={parentId} onValueChange={setParentId}>
              <SelectTrigger>
                <SelectValue placeholder="No parent" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_PARENT}>No parent</SelectItem>
                {parentOptions.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.key} · {p.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {parentOptions.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No eligible parents for a {kind.replace("_", " ")}.
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending || title.trim() === ""}>
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
