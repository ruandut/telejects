# Frontend rules

React 19 + Vite+ (`vp`) + TanStack Router/Query + Zustand + shadcn + Tailwind v4, pnpm. The root
CLAUDE.md applies too.

## Layout

- Feature-based. `src/features/<feature>/` holds that feature's `api.ts` (query and mutation
  hooks), components and types.
- `src/network/` is the only place that calls `fetch` (or opens a `WebSocket`): it attaches the
  JWT and `X-Realm`, refreshes once on 401 and raises `ApiError`. Features never call `fetch`.
- Change company only through `enterRealm()` (`src/features/realms/realm-gate.tsx`), which drops
  the old company's cached data. Signed-in screens render inside `RealmGate`.
- Show and hide things with `usePermission(code)` (`src/features/realms/permissions.ts`), never
  by a role's name or key. The server checks every request itself; the UI only follows.
- `src/routes/` holds thin route files that compose feature components. Signed-in screens live
  under `src/routes/_app/`, one folder per screen. `src/routeTree.gen.ts` is generated.
- `src/stores/` holds Zustand stores (tokens only in `auth.ts`; who the user is comes from
  `/api/auth/me/` through Query). `src/components/` holds shared components;
  `src/components/ui/` is shadcn (add with `vpx shadcn@latest add <name>`, don't hand-edit
  unless needed).

## Look and feel

- Every screen works in light and dark mode. Use the theme tokens in `src/index.css` (`primary`,
  `muted`, `brand-accent`, ...), not hard-coded colours. The palette is a placeholder until the
  brand is decided; changing it should only touch `index.css`, the favicon and `wordmark.tsx`.
- Build for phone width too. Pages must not scroll sideways.
- Figures use `tabular-nums`.

## Commands

- `vp dev`, `vp build`, `vp check` (lint, format, types), `vp fmt`. From the repo root,
  `make web` and `make check`.
