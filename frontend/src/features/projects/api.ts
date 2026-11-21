import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/network/client";

import type { Level, Person, PersonAccess, Project, ProjectInput, ProjectMember } from "./types";

const ROOT = ["projects"];

export function useProjects(options: { archived?: boolean } = {}) {
  return useQuery({
    queryKey: [...ROOT, "list", options.archived ?? false],
    queryFn: () => api<Project[]>(`/api/projects/${options.archived ? "?archived=1" : ""}`),
  });
}

export function useProject(id: number) {
  return useQuery({ queryKey: [...ROOT, id], queryFn: () => api<Project>(`/api/projects/${id}/`) });
}

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectInput) =>
      api<Project>("/api/projects/", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: (project) => {
      toast.success(`${project.name} created`);
      void client.invalidateQueries({ queryKey: ROOT });
    },
  });
}

export function useUpdateProject(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectInput) =>
      api<Project>(`/api/projects/${id}/`, { method: "PATCH", body: JSON.stringify(input) }),
    onSuccess: (project) => {
      client.setQueryData([...ROOT, id], project);
      void client.invalidateQueries({ queryKey: [...ROOT, "list"] });
      void client.invalidateQueries({ queryKey: ["analytics", "portfolio"] });
    },
  });
}

export function useDeleteProject(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<null>(`/api/projects/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Project deleted");
      void client.invalidateQueries({ queryKey: ROOT });
    },
  });
}

export function useProjectMembers(id: number) {
  return useQuery({
    queryKey: [...ROOT, id, "members"],
    queryFn: () => api<ProjectMember[]>(`/api/projects/${id}/members/`),
  });
}

/** Everyone who can open the project: who a people column or a mention can name. */
export function useProjectPeople(id: number) {
  return useQuery({
    queryKey: [...ROOT, id, "people"],
    queryFn: () => api<Person[]>(`/api/projects/${id}/people/`),
  });
}

export function useShareCandidates(id: number, enabled: boolean) {
  return useQuery({
    queryKey: [...ROOT, id, "candidates"],
    queryFn: () => api<Person[]>(`/api/projects/${id}/candidates/`),
    enabled,
  });
}

export function useShare(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { membership: number; level: Level | null }) =>
      api<ProjectMember[]>(`/api/projects/${id}/members/`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: (members) => {
      client.setQueryData([...ROOT, id, "members"], members);
      void client.invalidateQueries({ queryKey: [...ROOT, id, "people"] });
    },
    onError: (error) => toast.error(error.message),
  });
}

export function usePersonAccess(membership: number) {
  return useQuery({
    queryKey: [...ROOT, "access", membership],
    queryFn: () => api<PersonAccess>(`/api/projects/access/?membership=${membership}`),
  });
}

export function useSetPersonAccess(membership: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { project: number; level: Level | null }) =>
      api<null>("/api/projects/access/", {
        method: "POST",
        body: JSON.stringify({ ...input, membership }),
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: [...ROOT, "access", membership] }),
    onError: (error) => toast.error(error.message),
  });
}
