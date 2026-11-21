import { initials, personColour } from "@/lib/colours";
import { cn } from "@/lib/utils";

export function Avatar({
  id,
  name,
  className,
  ring,
  label,
}: {
  id: number;
  name: string;
  className?: string;
  ring?: boolean;
  /** What a screen reader and tooltip say, when more than the name. */
  label?: string;
}) {
  return (
    <span
      title={label ?? name}
      aria-label={label ?? name}
      className={cn(
        "inline-flex size-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white select-none",
        ring && "ring-2 ring-background",
        className,
      )}
      style={{ background: personColour(id) }}
    >
      {initials(name)}
    </span>
  );
}

export function AvatarStack({
  people,
  max = 3,
}: {
  people: { id: number; name: string }[];
  max?: number;
}) {
  const shown = people.slice(0, max);
  const more = people.length - shown.length;
  return (
    <span className="flex items-center -space-x-1.5">
      {shown.map((p) => (
        <Avatar key={p.id} id={p.id} name={p.name} ring />
      ))}
      {more > 0 && (
        <span className="inline-flex size-6 items-center justify-center rounded-full bg-muted text-[10px] font-medium ring-2 ring-background">
          +{more}
        </span>
      )}
    </span>
  );
}
