/** Who can work on a project, and at what level. Managers of every project are listed apart. */
import { UserPlus } from "lucide-react";
import { useState } from "react";

import { NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar } from "@/features/boards/components/avatar";

import { useProjectMembers, useProjectPeople, useShare, useShareCandidates } from "../api";
import { LEVEL_HINTS, LEVEL_LABELS, type Level, type Project } from "../types";

const LEVELS: Level[] = ["view", "edit", "manage"];

export function AccessPanel({ project }: { project: Project }) {
  const canManage = project.my_level === "manage";
  const members = useProjectMembers(project.id);
  const people = useProjectPeople(project.id);
  const candidates = useShareCandidates(project.id, canManage);
  const share = useShare(project.id);
  const [person, setPerson] = useState("");
  const [level, setLevel] = useState<Level>("edit");
  const shared = new Set(members.data?.map((m) => m.person.id));
  const managersOfAll = (people.data ?? []).filter((p) => !shared.has(p.id));
  const available = (candidates.data ?? []).filter((c) => !shared.has(c.id));

  return (
    <div className="grid max-w-3xl gap-6">
      {canManage && (
        <section className="grid gap-2 rounded-xl border bg-card p-4" aria-label="Share">
          <h2 className="font-medium">Share this project</h2>
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_10rem_auto]">
            <NativeSelect
              aria-label="Person"
              value={person}
              onChange={(e) => setPerson(e.target.value)}
            >
              <option value="">Choose someone in the company</option>
              {available.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.email})
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label="Level"
              value={level}
              onChange={(e) => setLevel(e.target.value as Level)}
            >
              {LEVELS.map((l) => (
                <option key={l} value={l}>
                  {LEVEL_LABELS[l]}
                </option>
              ))}
            </NativeSelect>
            <Button
              disabled={!person || share.isPending}
              onClick={() =>
                share.mutate(
                  { membership: Number(person), level },
                  { onSuccess: () => setPerson("") },
                )
              }
            >
              <UserPlus /> Share
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">{LEVEL_HINTS[level]}.</p>
        </section>
      )}
      <section aria-label="People on this project">
        <h2 className="mb-2 font-medium">Shared with</h2>
        {members.isLoading && <Skeleton className="h-24" />}
        <ul className="divide-y rounded-xl border bg-card">
          {members.data?.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <Avatar id={m.person.id} name={m.person.name} className="size-8 text-xs" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{m.person.name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {m.person.email}
                </span>
              </span>
              {canManage ? (
                <NativeSelect
                  aria-label={`${m.person.name}'s level`}
                  className="w-40"
                  value={m.level}
                  onChange={(e) =>
                    share.mutate({
                      membership: m.person.id,
                      level: e.target.value === "remove" ? null : (e.target.value as Level),
                    })
                  }
                >
                  {LEVELS.map((l) => (
                    <option key={l} value={l}>
                      {LEVEL_LABELS[l]}
                    </option>
                  ))}
                  <option value="remove">Remove access</option>
                </NativeSelect>
              ) : (
                <span className="text-sm text-muted-foreground">{LEVEL_LABELS[m.level]}</span>
              )}
            </li>
          ))}
          {members.data?.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-muted-foreground">
              Not shared with anyone yet.
            </li>
          )}
        </ul>
      </section>
      {managersOfAll.length > 0 && (
        <section aria-label="Project managers">
          <h2 className="font-medium">Also has full access</h2>
          <p className="mb-2 text-sm text-muted-foreground">
            People whose role lets them manage every project.
          </p>
          <div className="flex flex-wrap gap-2">
            {managersOfAll.map((p) => (
              <span
                key={p.id}
                className="inline-flex items-center gap-2 rounded-full border bg-card py-1 pr-3 pl-1 text-sm"
              >
                <Avatar id={p.id} name={p.name} /> {p.name}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
