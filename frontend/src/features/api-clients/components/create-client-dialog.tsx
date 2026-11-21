import { Check, Copy, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Field, FormError } from "@/components/form";
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
import { Skeleton } from "@/components/ui/skeleton";
import type { Permission } from "@/features/auth/types";
import { cn } from "@/lib/utils";

import { useCreateApiClient, useGrantablePermissions } from "../api";
import type { CreatedApiClient } from "../types";

/** What a client for Rapid's single-site endpoints needs. */
const SUGGESTED: Permission[] = ["feasibilities.run", "feasibilities.quote"];

/** Create an API client, then show its secret, once. Mount it fresh each time it opens. */
export function CreateClientDialog({ onClose }: { onClose: () => void }) {
  const [created, setCreated] = useState<CreatedApiClient | null>(null);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        {created ? (
          <ClientSecret client={created} onClose={onClose} />
        ) : (
          <ClientForm onCreated={setCreated} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ClientForm({
  onCreated,
  onClose,
}: {
  onCreated: (client: CreatedApiClient) => void;
  onClose: () => void;
}) {
  const grantable = useGrantablePermissions();
  const create = useCreateApiClient();
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<Permission[] | null>(null);
  const offered = grantable.data ?? [];
  const picked =
    chosen ?? SUGGESTED.filter((code) => offered.some((permission) => permission.code === code));

  const toggle = (code: Permission) =>
    setChosen(picked.includes(code) ? picked.filter((c) => c !== code) : [...picked, code]);

  return (
    <>
      <DialogHeader>
        <DialogTitle>New server credentials</DialogTitle>
        <DialogDescription>
          For a system that talks to Telejects directly. It can only do what you give it, and only
          what you may do yourself.
        </DialogDescription>
      </DialogHeader>
      <form
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate({ name: name.trim(), permissions: picked }, { onSuccess: onCreated });
        }}
      >
        <Field label="Name" htmlFor="client-name" hint="Who or what uses it, e.g. 'Quoting tool'.">
          <Input
            id="client-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="off"
            autoFocus
            required
            maxLength={100}
          />
        </Field>

        <fieldset className="grid gap-2">
          <legend className="mb-2 text-sm font-medium">What it may do</legend>
          {grantable.data ? (
            offered.map((permission) => {
              const checked = picked.includes(permission.code);
              return (
                <label
                  key={permission.code}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors has-focus-visible:ring-3 has-focus-visible:ring-ring/50",
                    checked ? "border-primary bg-accent" : "hover:bg-muted",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(permission.code)}
                    className="mt-0.5 accent-primary"
                  />
                  <span className="grid min-w-0 gap-0.5">
                    <span className="text-sm">{permission.label}</span>
                    <span className="truncate font-mono text-xs text-muted-foreground">
                      {permission.code}
                    </span>
                  </span>
                </label>
              );
            })
          ) : (
            <Skeleton className="h-40 w-full" />
          )}
        </fieldset>

        <FormError error={create.error ?? grantable.error} />

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={create.isPending || picked.length === 0}>
            {create.isPending ? "Creating…" : "Create client"}
          </Button>
        </DialogFooter>
      </form>
    </>
  );
}

function ClientSecret({ client, onClose }: { client: CreatedApiClient; onClose: () => void }) {
  return (
    <>
      <DialogHeader>
        <DialogTitle>{client.name} is ready</DialogTitle>
        <DialogDescription>
          Give these to the system that will use it. It asks for a token with them, then sends the
          token with each request.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4">
        <Copyable label="Client ID" value={client.client_id} />
        <Copyable label="Client secret" value={client.client_secret} />
        <p className="flex gap-2 rounded-lg border border-brand-accent/40 bg-brand-accent/10 p-3 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-brand-accent" />
          <span>
            This is the only time the secret is shown. Telejects keeps only a scrambled copy, so if
            it's lost, revoke this client and create another.
          </span>
        </p>
      </div>
      <DialogFooter>
        <Button onClick={onClose}>I've saved it</Button>
      </DialogFooter>
    </>
  );
}

function Copyable({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const id = `copy-${label.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <Field label={label} htmlFor={id}>
      <div className="flex gap-2">
        <Input
          id={id}
          value={value}
          readOnly
          className="font-mono text-xs"
          onFocus={(e) => e.target.select()}
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label={`Copy ${label.toLowerCase()}`}
          onClick={() => {
            void navigator.clipboard.writeText(value).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          {copied ? <Check /> : <Copy />}
        </Button>
      </div>
    </Field>
  );
}
