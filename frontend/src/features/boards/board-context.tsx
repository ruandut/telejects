import { createContext, useContext } from "react";

import type { Person } from "@/features/projects/types";

import type { Board, Present } from "./types";

export type BoardCtx = {
  board: Board;
  people: Map<number, Person>;
  peopleList: Person[];
  canEdit: boolean;
  canManage: boolean;
  present: Present[];
  me: number | null;
  /** Tell the others which cell I'm in (null when I leave it). */
  focus: (item: number | null, column: string | null) => void;
  openItem: (id: number) => void;
};

export const BoardContext = createContext<BoardCtx | null>(null);

export function useBoardCtx(): BoardCtx {
  const ctx = useContext(BoardContext);
  if (!ctx) throw new Error("useBoardCtx outside a board");
  return ctx;
}
