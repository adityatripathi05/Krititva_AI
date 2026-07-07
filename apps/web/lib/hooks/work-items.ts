"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { clientApi } from "@/lib/api/client";
import type {
  HierarchyRule,
  WorkItem,
  WorkflowState,
  WorkflowTransition,
} from "@/lib/api/types";

export const workItemsKey = (projectId: string) => ["work-items", projectId] as const;

export function useStates(projectId: string) {
  return useQuery({
    queryKey: ["states", projectId],
    queryFn: () => clientApi<WorkflowState[]>(`/projects/${projectId}/workflow/states`),
  });
}

export function useTransitions(projectId: string) {
  return useQuery({
    queryKey: ["transitions", projectId],
    queryFn: () =>
      clientApi<WorkflowTransition[]>(`/projects/${projectId}/workflow/transitions`),
  });
}

export function useHierarchyRules(projectId: string) {
  return useQuery({
    queryKey: ["hierarchy", projectId],
    queryFn: () => clientApi<HierarchyRule[]>(`/projects/${projectId}/hierarchy-rules`),
  });
}

export function useWorkItems(projectId: string) {
  return useQuery({
    queryKey: workItemsKey(projectId),
    queryFn: () => clientApi<WorkItem[]>(`/projects/${projectId}/work_items`),
  });
}

interface TransitionArgs {
  itemId: string;
  toStateId: string;
}

/** Optimistic state transition; rolls back the cache on a 4xx from the engine. */
export function useTransitionItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, toStateId }: TransitionArgs) =>
      clientApi<WorkItem>(`/projects/${projectId}/work_items/${itemId}/transitions`, {
        method: "POST",
        body: JSON.stringify({ to_state_id: toStateId }),
      }),
    onMutate: async ({ itemId, toStateId }) => {
      await qc.cancelQueries({ queryKey: workItemsKey(projectId) });
      const prev = qc.getQueryData<WorkItem[]>(workItemsKey(projectId));
      qc.setQueryData<WorkItem[]>(workItemsKey(projectId), (old) =>
        old?.map((w) => (w.id === itemId ? { ...w, state_id: toStateId } : w)),
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(workItemsKey(projectId), ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: workItemsKey(projectId) }),
  });
}

interface RerankArgs {
  itemId: string;
  beforeId: string | null;
  afterId: string | null;
  optimistic: WorkItem[];
}

/** Optimistic rerank; the caller supplies the reordered array for the cache. */
export function useRerankItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, beforeId, afterId }: RerankArgs) =>
      clientApi<WorkItem>(`/projects/${projectId}/work_items/${itemId}/rerank`, {
        method: "POST",
        body: JSON.stringify({ before_id: beforeId, after_id: afterId }),
      }),
    onMutate: async ({ optimistic }) => {
      await qc.cancelQueries({ queryKey: workItemsKey(projectId) });
      const prev = qc.getQueryData<WorkItem[]>(workItemsKey(projectId));
      qc.setQueryData<WorkItem[]>(workItemsKey(projectId), optimistic);
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(workItemsKey(projectId), ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: workItemsKey(projectId) }),
  });
}

interface CreateArgs {
  kind: string;
  title: string;
  parent_id: string | null;
}

export function useCreateWorkItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateArgs) =>
      clientApi<WorkItem>(`/projects/${projectId}/work_items`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: workItemsKey(projectId) }),
  });
}
