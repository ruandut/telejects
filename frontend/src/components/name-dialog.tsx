import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Asks for a name (a new board, renaming a view). The app's own dialog, never the browser's
 * `prompt()`. Render it while it should be open; it calls `onClose` when dismissed.
 */
export function NameDialog({
  title,
  description,
  label = "Name",
  initial = "",
  placeholder,
  confirmLabel = "Save",
  maxLength = 120,
  pending = false,
  onSubmit,
  onClose,
}: {
  title: string;
  description?: string;
  label?: string;
  initial?: string;
  placeholder?: string;
  confirmLabel?: string;
  maxLength?: number;
  pending?: boolean;
  onSubmit: (name: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(initial);
  const trimmed = name.trim();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (trimmed) onSubmit(trimmed);
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="name-dialog-input">{label}</Label>
            <Input
              id="name-dialog-input"
              value={name}
              placeholder={placeholder}
              maxLength={maxLength}
              autoFocus
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || pending}>
              {confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
