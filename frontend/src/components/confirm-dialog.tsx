import { useState, type ReactNode } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

/**
 * Asks before something that can't be undone. Either wrap the button that opens it
 * (`children`), or, from a dropdown menu, control it with `open` / `onOpenChange` and render it
 * outside the menu: a dialog inside a menu goes away when the menu closes.
 *
 * `typeToConfirm` asks for that text (a project's name) before the action is enabled, for the
 * deletes that take a lot with them.
 */
export function ConfirmDialog({
  children,
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  typeToConfirm,
  onConfirm,
}: {
  children?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: ReactNode;
  description: ReactNode;
  confirmLabel: ReactNode;
  cancelLabel?: ReactNode;
  destructive?: boolean;
  typeToConfirm?: string;
  onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const ready = !typeToConfirm || typed.trim() === typeToConfirm.trim();
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setTyped("");
        onOpenChange?.(next);
      }}
    >
      {children && <AlertDialogTrigger asChild>{children}</AlertDialogTrigger>}
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {typeToConfirm && (
          <div className="grid gap-2">
            <Label htmlFor="confirm-dialog-text">
              Type <span className="font-semibold">{typeToConfirm}</span> to confirm
            </Label>
            <Input
              id="confirm-dialog-text"
              value={typed}
              autoComplete="off"
              autoFocus
              onChange={(e) => setTyped(e.target.value)}
            />
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            variant={destructive ? "destructive" : "default"}
            disabled={!ready}
            onClick={onConfirm}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
