# Telejects

A monorepo on the same stack as eden-tracker:

```
backend/     Django + DRF + SimpleJWT (uv). One app per concern under backend/apps/
frontend/    React + Vite+ + TanStack Router/Query + Zustand + shadcn
infra/       Postgres init scripts
scripts/     Local setup helpers
specs/       One spec per feature
```

## Setup

Needs Docker, [uv](https://docs.astral.sh/uv/) and pnpm.

```bash
make setup
```

That writes a gitignored `.env` with generated local secrets, starts Postgres and Hatchet,
installs dependencies, migrates, creates a Hatchet token and seeds a local sign-in. The sign-in
is `DEV_ADMIN_EMAIL` / `DEV_ADMIN_PASSWORD` in `.env`.

Then, in three terminals:

```bash
make api
```

```bash
make web
```

```bash
make worker
```

The ports are fixed, and offset from eden-tracker's so both can run at once. `make api` and
`make web` take their port over from whatever still holds it, and `make worker` replaces an
earlier worker. `make stop` stops all three.

| What | Where |
|---|---|
| App | http://localhost:5184 |
| API | http://localhost:8010/api/ |
| Django admin | http://localhost:8010/admin/ |
| Hatchet dashboard | http://localhost:8892 |
| Postgres | localhost:5436 |

## Checks

```bash
make test
```

```bash
make check
```

## Secrets

Nothing sensitive is committed, ever: no passwords, tokens, keys or env values. Every
environment value lives in the gitignored `.env` that `scripts/init_env.sh` generates. See
[CLAUDE.md](CLAUDE.md) for the rules.
