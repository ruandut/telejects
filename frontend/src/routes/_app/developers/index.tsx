import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/developers/")({
  beforeLoad: () => {
    throw redirect({ to: "/developers/credentials", replace: true });
  },
});
