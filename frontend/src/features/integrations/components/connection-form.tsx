import { useState } from "react";

import { Field, FormError, PasswordInput } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import type { Connection, Connector } from "../types";

/**
 * The form a connector's definition asks for. Secrets are never shown: on an existing
 * connection, leaving one empty keeps it.
 */
export function ConnectionForm({
  connector,
  connection,
  pending,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  connector: Connector;
  connection: Connection | null;
  pending: boolean;
  error: Error | null;
  submitLabel: string;
  onSubmit: (name: string, fields: Record<string, string>) => void;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(connection?.name ?? connector.name);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      connector.fields.map((f) => [
        f.key,
        f.type === "secret" ? "" : (connection?.settings[f.key] ?? ""),
      ]),
    ),
  );

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(name.trim(), values);
      }}
    >
      <Field label="Name" htmlFor="connection-name" hint="How this account shows in Telejects.">
        <Input
          id="connection-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoComplete="off"
          required
        />
      </Field>
      {connector.fields.map((field) => {
        const id = `connection-${field.key}`;
        const isSet = connection?.secrets_set.includes(field.key);
        const hint =
          field.type === "secret" && isSet
            ? `Saved. Leave empty to keep it. ${field.help}`.trim()
            : field.help || undefined;
        const common = {
          id,
          value: values[field.key] ?? "",
          autoComplete: "off",
          required: field.required && !(field.type === "secret" && isSet),
          onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
            setValues((v) => ({ ...v, [field.key]: e.target.value })),
        };
        return (
          <Field key={field.key} label={field.label} htmlFor={id} hint={hint}>
            {field.type === "secret" ? (
              <PasswordInput {...common} placeholder={isSet ? "••••••••" : undefined} />
            ) : (
              <Input {...common} type={field.type === "email" ? "email" : "text"} />
            )}
          </Field>
        );
      })}
      <FormError error={error} />
      <div className="flex flex-wrap justify-end gap-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
