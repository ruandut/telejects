import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/network/client";

import type { Automation, AutomationInput, Run } from "./types";

const ROOT = ["automations"];

export function useAutomations(boardId: number) {
  return useQuery({
    queryKey: [...ROOT, boardId],
    queryFn: () => api<Automation[]>(`/api/automations/?board=${boardId}`),
  });
}

export function useRuns(id: number | null) {
  return useQuery({
    queryKey: [...ROOT, "runs", id],
    queryFn: () => api<Run[]>(`/api/automations/${id}/runs/`),
    enabled: id !== null,
    refetchInterval: 15_000,
  });
}

export function useSaveAutomation(boardId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: Partial<AutomationInput> & { id?: number }) =>
      id
        ? api<Automation>(`/api/automations/${id}/`, {
            method: "PATCH",
            body: JSON.stringify(input),
          })
        : api<Automation>("/api/automations/", {
            method: "POST",
            body: JSON.stringify({ ...input, board: boardId }),
          }),
    onSuccess: () => void client.invalidateQueries({ queryKey: [...ROOT, boardId] }),
  });
}

export function useDeleteAutomation(boardId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<null>(`/api/automations/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Automation deleted");
      void client.invalidateQueries({ queryKey: [...ROOT, boardId] });
    },
    onError: (error) => toast.error(error.message),
  });
}
