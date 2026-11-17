import { useState } from "react";

import { Field, FormError, PasswordInput } from "@/components/form";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/network/errors";

import { useChangePassword } from "../api";

type FieldErrors = { current_password?: string[]; new_password?: string[] };

/** Change my password with my current one. The new one is typed twice and only sent when both
 * match. */
export function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const change = useChangePassword();

  const fields: FieldErrors =
    change.error instanceof ApiError && change.error.status === 400
      ? (change.error.body as FieldErrors)
      : {};
  // Anything that isn't about one field, like being told to wait.
  const other = change.error && !fields.current_password && !fields.new_password;
  const mismatch = again !== "" && again !== next;

  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (mismatch) return;
        change.mutate(
          { current_password: current, new_password: next },
          {
            onSuccess: () => {
              setCurrent("");
              setNext("");
              setAgain("");
            },
          },
        );
      }}
    >
      <Field label="Current password" htmlFor="current-password">
        <PasswordInput
          id="current-password"
          autoComplete="current-password"
          required
          value={current}
          aria-invalid={Boolean(fields.current_password)}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <FieldMessages messages={fields.current_password} />
      </Field>
      <Field
        label="New password"
        htmlFor="new-password"
        hint="At least 12 characters, not a common one, not all numbers, and not like your email."
      >
        <PasswordInput
          id="new-password"
          autoComplete="new-password"
          required
          value={next}
          aria-invalid={Boolean(fields.new_password)}
          onChange={(event) => setNext(event.target.value)}
        />
        <FieldMessages messages={fields.new_password} />
      </Field>
      <Field label="New password again" htmlFor="new-password-again">
        <PasswordInput
          id="new-password-again"
          autoComplete="new-password"
          required
          value={again}
          aria-invalid={mismatch}
          onChange={(event) => setAgain(event.target.value)}
        />
        {mismatch && <FieldMessages messages={["The two new passwords don't match."]} />}
      </Field>
      {other && <FormError error={change.error} />}
      <div className="flex justify-end">
        <Button
          type="submit"
          disabled={!current || !next || !again || mismatch || change.isPending}
        >
          {change.isPending ? "Changing…" : "Change password"}
        </Button>
      </div>
    </form>
  );
}

function FieldMessages({ messages }: { messages?: string[] }) {
  if (!messages?.length) return null;
  return (
    <ul role="alert" className="grid gap-0.5 text-sm text-destructive">
      {messages.map((message) => (
        <li key={message}>{message}</li>
      ))}
    </ul>
  );
}
