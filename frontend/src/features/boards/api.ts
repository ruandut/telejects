import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useRef } from "react";
import { toast } from "sonner";

import { useLive } from "@/features/realms/live";
import { api } from "@/network/client";

import type {
  Activity,
  Board,
  BoardSummary,
  BoardView,
  Column,
  Group,
  ImportResult,
  Item,
  ItemUpdate,
  Present,
  Template,
} from "./types";

const ROOT = ["boards"];
const itemsKey = (boardId: number) => [...ROOT, boardId, "items"];

export function useBoards(projectId: number) {
  return useQuery({
    queryKey: [...ROOT, "of", projectId],
    queryFn: () => api<BoardSummary[]>(`/api/boards/?project=${projectId}`),
  });
}

export function useBoard(id: number) {
  return useQuery({ queryKey: [...ROOT, id], queryFn: () => api<Board>(`/api/boards/${id}/`) });
}

export function useItems(boardId: number, archived = false) {
  return useQuery({
    queryKey: archived ? [...itemsKey(boardId), "archived"] : itemsKey(boardId),
    queryFn: () => api<Item[]>(`/api/boards/${boardId}/items/${archived ? "?archived=1" : ""}`),
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: [...ROOT, "templates"],
    queryFn: () => api<Template[]>("/api/boards/templates/"),
    staleTime: Infinity,
  });
}

/** Put fresh items into the board's cached list (and drop removed ones). */
export function mergeItems(
  client: QueryClient,
  boardId: number,
  items: Item[],
  removed: number[] = [],
) {
  client.setQueryData<Item[]>(itemsKey(boardId), (current) => {
    if (!current) return current;
    const fresh = new Map(items.filter((i) => !i.archived_at).map((i) => [i.id, i]));
    const gone = new Set(removed);
    for (const item of items) if (item.archived_at) gone.add(item.id);
    const next = current.filter((i) => !gone.has(i.id)).map((i) => fresh.get(i.id) ?? i);
    const known = new Set(current.map((i) => i.id));
    for (const item of fresh.values()) if (!known.has(item.id)) next.push(item);
    return next;
  });
}

/**
 * The board's changes arrive over the socket, built by the server for me with the same
 * serializer as the API, and go straight into the cache. A change to the board itself, or a
 * reconnect, refetches.
 */
export function useBoardLive(boardId: number) {
  const client = useQueryClient();
  useLive("board", boardId, (message) => {
    if (message.type === "data") {
      const { items, removed } = message.data as { items: Item[]; removed: number[] };
      mergeItems(client, boardId, items, removed);
      void client.invalidateQueries({ queryKey: [...ROOT, boardId, "item"] });
      void client.invalidateQueries({ queryKey: [...ROOT, "of"] });
    } else if (message.type === "changed" || message.type === "reconnected") {
      void client.invalidateQueries({ queryKey: [...ROOT, boardId] });
      void client.invalidateQueries({ queryKey: [...ROOT, "of"] });
      // Sharing changes who a people column can name.
      void client.invalidateQueries({ queryKey: ["projects"] });
    }
  });
}

function useBoardMutation<I, O>(
  boardId: number,
  request: (input: I) => Promise<O>,
  refetchBoard = true,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      if (refetchBoard)
        void client.invalidateQueries({ queryKey: [...ROOT, boardId], exact: true });
    },
    onError: (error) => toast.error(error.message),
  });
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export function useUpdateBoard(boardId: number) {
  return useBoardMutation(
    boardId,
    (input: Partial<Pick<Board, "name" | "description" | "status_column" | "due_column">>) =>
      api<Board>(`/api/boards/${boardId}/`, json("PATCH", input)),
  );
}

export function useCreateBoard(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; template: string; feasibility_run?: number }) =>
      api<Board>("/api/boards/", json("POST", { ...input, project: projectId })),
    onSuccess: () => void client.invalidateQueries({ queryKey: [...ROOT, "of", projectId] }),
  });
}

/** A new board from a spreadsheet's rows (a monday.com export or a CSV). */
export function useBoardFromFile(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; rows: string[][]; project?: number }) =>
      api<Board & { import: ImportResult }>(
        "/api/boards/from-file/",
        json("POST", { project: projectId, ...input }),
      ),
    onSuccess: (_board, input) =>
      void client.invalidateQueries({ queryKey: [...ROOT, "of", input.project ?? projectId] }),
  });
}

export function useDeleteBoard(boardId: number, projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<null>(`/api/boards/${boardId}/`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: [...ROOT, "of", projectId] }),
    onError: (error) => toast.error(error.message),
  });
}

export function useGroupActions(boardId: number) {
  return {
    create: useBoardMutation(boardId, (input: { name: string; colour?: string; top?: boolean }) =>
      api<Group>("/api/boards/groups/", json("POST", { ...input, board: boardId })),
    ),
    update: useBoardMutation(boardId, ({ id, ...input }: Partial<Group> & { id: number }) =>
      api<Group>(`/api/boards/groups/${id}/`, json("PATCH", input)),
    ),
    remove: useBoardMutation(boardId, (id: number) =>
      api<null>(`/api/boards/groups/${id}/`, { method: "DELETE" }),
    ),
  };
}

export function useColumnActions(boardId: number) {
  const client = useQueryClient();
  const refreshItems = () => void client.invalidateQueries({ queryKey: itemsKey(boardId) });
  const create = useBoardMutation(boardId, (input: Partial<Column> & { after?: string | null }) =>
    api<Column>("/api/boards/columns/", json("POST", { ...input, board: boardId })).then((c) => {
      refreshItems();
      return c;
    }),
  );
  const update = useBoardMutation(boardId, ({ id, ...input }: Partial<Column> & { id: number }) =>
    api<Column>(`/api/boards/columns/${id}/`, json("PATCH", input)).then((c) => {
      refreshItems();
      return c;
    }),
  );
  const remove = useBoardMutation(boardId, (id: number) =>
    api<null>(`/api/boards/columns/${id}/`, { method: "DELETE" }).then(refreshItems),
  );
  return { create, update, remove };
}

export function useViewActions(boardId: number) {
  return {
    create: useBoardMutation(boardId, (input: Omit<BoardView, "id" | "position">) =>
      api<BoardView>("/api/boards/views/", json("POST", { ...input, board: boardId })),
    ),
    update: useBoardMutation(boardId, ({ id, ...input }: Partial<BoardView> & { id: number }) =>
      api<BoardView>(`/api/boards/views/${id}/`, json("PATCH", input)),
    ),
    remove: useBoardMutation(boardId, (id: number) =>
      api<null>(`/api/boards/views/${id}/`, { method: "DELETE" }),
    ),
  };
}

export function useItemActions(boardId: number) {
  const client = useQueryClient();
  const merge = (item: Item) => mergeItems(client, boardId, [item]);

  const create = useMutation({
    mutationFn: (input: {
      name: string;
      group?: number;
      values?: Record<string, unknown>;
      top?: boolean;
    }) => api<Item>(`/api/boards/${boardId}/items/`, json("POST", input)),
    onSuccess: merge,
    onError: (error) => toast.error(error.message),
  });

  /** One or more cells, saved at once in the cache and then on the server. */
  const setValues = useMutation({
    mutationFn: ({ id, values }: { id: number; values: Record<string, unknown> }) =>
      api<Item>(`/api/boards/items/${id}/values/`, json("PATCH", values)),
    onMutate: ({ id, values }) => {
      const before = client.getQueryData<Item[]>(itemsKey(boardId))?.find((i) => i.id === id);
      if (before) {
        const next = { ...before.values };
        for (const [key, value] of Object.entries(values)) {
          if (value === null || value === "" || (Array.isArray(value) && !value.length))
            delete next[key];
          else next[key] = value;
        }
        merge({ ...before, values: next });
      }
      return { before };
    },
    onSuccess: merge,
    onError: (error, _input, context) => {
      if (context?.before) merge(context.before);
      toast.error(error.message);
    },
  });

  const update = useMutation({
    mutationFn: ({
      id,
      ...input
    }: {
      id: number;
      name?: string;
      group?: number;
      before?: number | null;
      after?: number | null;
    }) => api<Item>(`/api/boards/items/${id}/`, json("PATCH", input)),
    onMutate: ({ id, name, group }) => {
      const before = client.getQueryData<Item[]>(itemsKey(boardId))?.find((i) => i.id === id);
      if (before) merge({ ...before, name: name ?? before.name, group: group ?? before.group });
      return { before };
    },
    onSuccess: merge,
    onError: (error, _input, context) => {
      if (context?.before) merge(context.before);
      toast.error(error.message);
    },
  });

  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "archive" | "restore" | "duplicate" }) =>
      api<Item>(`/api/boards/items/${id}/${action}/`, { method: "POST" }),
    onSuccess: (item, { action }) => {
      merge(item);
      if (action === "restore") void client.invalidateQueries({ queryKey: itemsKey(boardId) });
      toast.success(
        action === "archive" ? "Archived" : action === "restore" ? "Restored" : "Duplicated",
      );
    },
    onError: (error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api<null>(`/api/boards/items/${id}/`, { method: "DELETE" }),
    onSuccess: (_r, id) => mergeItems(client, boardId, [], [id]),
    onError: (error) => toast.error(error.message),
  });

  const batch = useMutation({
    mutationFn: (input: {
      items: number[];
      action: string;
      group?: number;
      values?: Record<string, unknown>;
    }) => api<{ done: number }>(`/api/boards/${boardId}/batch/`, json("POST", input)),
    onSuccess: ({ done }) => {
      void client.invalidateQueries({ queryKey: itemsKey(boardId) });
      toast.success(`${done} item${done === 1 ? "" : "s"} updated`);
    },
    onError: (error) => toast.error(error.message),
  });

  const importRows = useMutation({
    mutationFn: (rows: { name: string; group?: number; values: Record<string, unknown> }[]) =>
      api<ImportResult>(`/api/boards/${boardId}/import/`, json("POST", { rows })),
    onSuccess: () => void client.invalidateQueries({ queryKey: itemsKey(boardId) }),
    onError: (error) => toast.error(error.message),
  });

  return { create, setValues, update, act, remove, batch, importRows };
}

export function useItemUpdates(itemId: number | null, boardId: number) {
  return useQuery({
    queryKey: [...ROOT, boardId, "item", itemId, "updates"],
    queryFn: () => api<ItemUpdate[]>(`/api/boards/items/${itemId}/updates/`),
    enabled: itemId !== null,
  });
}

export function useItemActivity(itemId: number | null, boardId: number) {
  return useQuery({
    queryKey: [...ROOT, boardId, "item", itemId, "activity"],
    queryFn: () => api<Activity[]>(`/api/boards/items/${itemId}/activity/`),
    enabled: itemId !== null,
  });
}

export function useBoardActivity(boardId: number, enabled: boolean) {
  return useQuery({
    queryKey: [...ROOT, boardId, "activity"],
    queryFn: () => api<Activity[]>(`/api/boards/${boardId}/activity/`),
    enabled,
  });
}

export function usePostUpdate(itemId: number, boardId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { body: string; mentions: number[] }) =>
      api<ItemUpdate>(`/api/boards/items/${itemId}/updates/`, json("POST", input)),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: [...ROOT, boardId, "item", itemId] }),
    onError: (error) => toast.error(error.message),
  });
}

export function useItemSearch(boardId: number | undefined, search: string) {
  return useQuery({
    queryKey: [...ROOT, "search", boardId, search],
    queryFn: () =>
      api<{ id: number; name: string }[]>(
        `/api/boards/items/search/?board=${boardId}&search=${encodeURIComponent(search)}`,
      ),
    enabled: !!boardId,
    placeholderData: (previous) => previous,
  });
}

// --- presence ------------------------------------------------------------------------------

function tabId(): string {
  try {
    const known = sessionStorage.getItem("telejects-tab");
    if (known) return known;
    const fresh = `tab-${crypto.randomUUID().slice(0, 12)}`;
    sessionStorage.setItem("telejects-tab", fresh);
    return fresh;
  } catch {
    return "tab-shared";
  }
}

const HEARTBEAT_MS = 20_000;

/**
 * Tell the board I'm here (every 20 s, and when I move to another cell), and listen for who
 * else is. Leaving the page says goodbye at once; a closed laptop times out on the server.
 */
export function usePresence(
  boardId: number,
  focus: { item: number | null; column: string | null },
) {
  const client = useQueryClient();
  const key = [...ROOT, boardId, "presence"];
  const tab = useRef(tabId());
  const query = useQuery({
    queryKey: key,
    queryFn: () => api<Present[]>(`/api/presence/?board=${boardId}`),
  });
  useLive("board_presence", boardId, (message) => {
    if (message.type === "data")
      client.setQueryData(key, (message.data as { people: Present[] }).people);
    else void client.invalidateQueries({ queryKey: key });
  });

  const beat = useEffectEvent(() => {
    void api<Present[]>(
      "/api/presence/",
      json("POST", { board: boardId, tab: tab.current, ...focus }),
    )
      .then((people) => client.setQueryData([...ROOT, boardId, "presence"], people))
      .catch(() => {});
  });

  useEffect(() => {
    const timer = setTimeout(() => beat(), 300);
    return () => clearTimeout(timer);
  }, [boardId, focus.item, focus.column]);

  useEffect(() => {
    const timer = setInterval(() => beat(), HEARTBEAT_MS);
    const leave = () =>
      void api("/api/presence/leave/", {
        ...json("POST", { board: boardId, tab: tab.current }),
        keepalive: true,
      }).catch(() => {});
    window.addEventListener("pagehide", leave);
    return () => {
      clearInterval(timer);
      window.removeEventListener("pagehide", leave);
      leave();
    };
  }, [boardId]);

  return query.data ?? [];
}
