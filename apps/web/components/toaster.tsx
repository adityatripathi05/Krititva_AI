"use client";

import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import { useToastStore } from "@/lib/toast";

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={cn(
            "pointer-events-auto flex items-start justify-between gap-3 rounded-md border p-3 text-sm shadow-lg",
            t.variant === "error" && "border-destructive bg-destructive text-destructive-foreground",
            t.variant === "success" && "border-border bg-primary text-primary-foreground",
            t.variant === "default" && "border-border bg-popover text-popover-foreground",
          )}
        >
          <span className="break-words">{t.message}</span>
          <button
            type="button"
            onClick={() => dismiss(t.id)}
            className="opacity-70 transition-opacity hover:opacity-100"
            aria-label="Dismiss"
          >
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
