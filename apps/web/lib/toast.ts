"use client";

import { create } from "zustand";

export type ToastVariant = "default" | "error" | "success";

export interface Toast {
  readonly id: number;
  readonly message: string;
  readonly variant: ToastVariant;
}

interface ToastStore {
  toasts: Toast[];
  push: (message: string, variant?: ToastVariant) => void;
  dismiss: (id: number) => void;
}

let counter = 0;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (message, variant = "default") => {
    counter += 1;
    const id = counter;
    set((s) => ({ toasts: [...s.toasts, { id, message, variant }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 4000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

/** Fire a toast from anywhere in a client component. */
export function toast(message: string, variant: ToastVariant = "default"): void {
  useToastStore.getState().push(message, variant);
}
