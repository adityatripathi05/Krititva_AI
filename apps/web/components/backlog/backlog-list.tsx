"use client";

import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";

import { WorkItemDialog } from "@/components/work-item-dialog";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { toast } from "@/lib/toast";
import { useRerankItem, useStates, useWorkItems } from "@/lib/hooks/work-items";
import type { WorkItem } from "@/lib/api/types";

function byRank(a: WorkItem, b: WorkItem): number {
  if (a.rank && b.rank) return a.rank < b.rank ? -1 : a.rank > b.rank ? 1 : 0;
  if (a.rank) return -1;
  if (b.rank) return 1;
  return a.seq - b.seq;
}

function Row({ item, stateLabel }: { readonly item: WorkItem; readonly stateLabel: string }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: item.id });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "flex items-center gap-3 rounded-md border border-border bg-card p-3",
        isDragging && "opacity-60",
      )}
    >
      <button
        type="button"
        className="cursor-grab text-muted-foreground active:cursor-grabbing"
        aria-label="Reorder"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>
      <span className="font-mono text-xs text-muted-foreground">{item.key}</span>
      <span className="flex-1 text-sm">{item.title}</span>
      <Badge variant="outline" className="capitalize">
        {item.kind.replace("_", " ")}
      </Badge>
      <Badge variant="secondary">{stateLabel}</Badge>
    </li>
  );
}

export function BacklogList({ projectId }: { readonly projectId: string }) {
  const items = useWorkItems(projectId);
  const states = useStates(projectId);
  const rerank = useRerankItem(projectId);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  if (items.isLoading || states.isLoading) {
    return (
      <div className="space-y-2 p-6">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  const ordered = [...(items.data ?? [])].sort(byRank);
  const stateLabel = new Map((states.data ?? []).map((s) => [s.id, s.label]));

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = ordered.findIndex((w) => w.id === active.id);
    const to = ordered.findIndex((w) => w.id === over.id);
    if (from === -1 || to === -1) return;

    const next = arrayMove(ordered, from, to);
    const idx = next.findIndex((w) => w.id === active.id);
    const beforeId = idx > 0 ? next[idx - 1]!.id : null;
    const afterId = idx < next.length - 1 ? next[idx + 1]!.id : null;

    rerank.mutate(
      { itemId: String(active.id), beforeId, afterId, optimistic: next },
      { onError: () => toast("Could not reorder that item.", "error") },
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 p-6">
      <div className="flex justify-end">
        <WorkItemDialog projectId={projectId} />
      </div>
      {ordered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No work items yet.</p>
      ) : (
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <SortableContext
            items={ordered.map((w) => w.id)}
            strategy={verticalListSortingStrategy}
          >
            <ul className="space-y-2">
              {ordered.map((w) => (
                <Row key={w.id} item={w} stateLabel={stateLabel.get(w.state_id) ?? "—"} />
              ))}
            </ul>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}
