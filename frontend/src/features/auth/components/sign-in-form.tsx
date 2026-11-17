import { LoaderCircle } from "lucide-react";
import { useState } from "react";

import { Field, FormError, PasswordInput } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { useSignIn } from "../api";

export function SignInForm({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useSignIn();

  return (
    <form
      className="grid gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        signIn.mutate({ email, password }, { onSuccess: onSignedIn });
      }}
    >
      <Field label="Email" htmlFor="email">
        <Input
          id="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoFocus
          placeholder="you@example.com"
          className="h-11 bg-card px-3.5 text-base md:text-sm"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </Field>

      <Field label="Password" htmlFor="password">
        <PasswordInput
          id="password"
          autoComplete="current-password"
          className="h-11 bg-card px-3.5 text-base md:text-sm"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>

      <FormError error={signIn.error} />

      <Button type="submit" size="lg" className="mt-1 h-11 text-sm" disabled={signIn.isPending}>
        {signIn.isPending && <LoaderCircle aria-hidden className="animate-spin" />}
        {signIn.isPending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
