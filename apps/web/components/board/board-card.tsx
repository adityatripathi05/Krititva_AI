"use client";

import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { WorkItem } from "@/lib/api/types";

export function BoardCard({ item }: { readonly item: WorkItem }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: item.id,
  });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform) }}
      {...listeners}
      {...attributes}
      className={cn(
        "cursor-grab rounded-md border border-border bg-card p-3 shadow-sm active:cursor-grabbing",
        isDragging && "opacity-50",
      )}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-muted-foreground">{item.key}</span>
        <Badge variant="outline" className="capitalize">
          {item.kind.replace("_", " ")}
        </Badge>
      </div>
      <p className="text-sm">{item.title}</p>
    </div>
  );
}
