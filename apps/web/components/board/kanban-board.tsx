"use client";

import {
  DndContext,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";

import { BoardCard } from "@/components/board/board-card";
import { WorkItemDialog } from "@/components/work-item-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { toast } from "@/lib/toast";
import {
  useStates,
  useTransitions,
  useTransitionItem,
  useWorkItems,
} from "@/lib/hooks/work-items";
import type { WorkflowState } from "@/lib/api/types";

function Column({
  state,
  children,
}: {
  readonly state: WorkflowState;
  readonly children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: state.id });
  return (
    <div className="flex w-72 shrink-0 flex-col">
      <div className="mb-2 flex items-center justify-between px-1">
        <h3 className="text-sm font-medium">{state.label}</h3>
      </div>
      <div
        ref={setNodeRef}
        className={cn(
          "flex min-h-24 flex-1 flex-col gap-2 rounded-lg border border-dashed border-border p-2 transition-colors",
          isOver && "border-foreground/40 bg-accent/40",
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function KanbanBoard({ projectId }: { readonly projectId: string }) {
  const states = useStates(projectId);
  const items = useWorkItems(projectId);
  const transitions = useTransitions(projectId);
  const transitionItem = useTransitionItem(projectId);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
  );

  if (states.isLoading || items.isLoading || transitions.isLoading) {
    return (
      <div className="flex gap-4 p-6">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-64 w-72" />
        ))}
      </div>
    );
  }

  const stateList = states.data ?? [];
  const itemList = items.data ?? [];
  const edges = transitions.data ?? [];

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const item = itemList.find((w) => w.id === active.id);
    const toStateId = String(over.id);
    if (!item || item.state_id === toStateId) return;

    const allowed = edges.some(
      (e) => e.from_state === item.state_id && e.to_state === toStateId,
    );
    if (!allowed) {
      toast("That move isn't allowed by this workflow.", "error");
      return;
    }
    transitionItem.mutate(
      { itemId: item.id, toStateId },
      {
        onError: (err) =>
          toast(
            `Transition rejected${
              err instanceof Error && err.message ? `: ${err.message}` : ""
            }`,
            "error",
          ),
      },
    );
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex justify-end">
        <WorkItemDialog projectId={projectId} />
      </div>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex gap-4 overflow-x-auto pb-4">
          {stateList.map((state) => (
            <Column key={state.id} state={state}>
              {itemList
                .filter((w) => w.state_id === state.id)
                .map((w) => (
                  <BoardCard key={w.id} item={w} />
                ))}
            </Column>
          ))}
        </div>
      </DndContext>
    </div>
  );
}
