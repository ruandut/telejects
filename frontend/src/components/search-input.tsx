import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** A search box with a magnifier, for filtering a list as you type. */
export function SearchInput({
  label,
  value,
  onChange,
  placeholder,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative min-w-0", className)}>
      <Search
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input
        type="search"
        aria-label={label}
        placeholder={placeholder}
        className="pl-8"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
