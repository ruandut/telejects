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
installs dependencies, migrates (which also loads the built-in connector definitions), creates a
Hatchet token and seeds a local sign-in. The sign-in is `DEV_ADMIN_EMAIL` / `DEV_ADMIN_PASSWORD`
in `.env`. Every provider whose Telejects key is set in `.env` (`PLATFORM_*`) is connected for
every company from the start; locally the Demo provider is too (`INTEGRATIONS_DEMO_ENABLED`), so
feasibility runs can be tried without real provider credentials. An older `.env` gets the new integrations
lines with `make env`.

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

`make seed` makes that sign-in the Admin of a first company, "Telejects Demo". Platform staff add
a real company, and invite its first Admin, with:

```bash
cd backend && uv run python manage.py create_company "Company name" admin@their-domain.example
```

Invitation emails are sent by the worker; without a mail server in `.env` they are printed to its
log, link included.

The ports are fixed, and offset from eden-tracker's so both can run at once. `make api` and
`make web` take their port over from whatever still holds it, and `make worker` replaces an
earlier worker. `make stop` stops all three.

| What | Where |
|---|---|
| App | http://localhost:5184 |
| API | http://localhost:8010/api/ |
| Django admin | http://localhost:8010/admin/ |
| Hatchet dashboard | http://localhost:8892 (sign in with `HATCHET_ADMIN_EMAIL` / `HATCHET_ADMIN_PASSWORD` in `.env`) |
| Postgres | localhost:5436 |

### Resetting Hatchet

Hatchet creates its dashboard admin from `.env` the first time its data is set up, so a changed
`HATCHET_ADMIN_PASSWORD` only applies after a reset. This wipes Hatchet's run history, not the
app's data:

```bash
docker compose rm -sf hatchet
```

```bash
docker compose exec postgres psql -U telejects -d telejects -c "DROP DATABASE hatchet WITH (FORCE);" -c "CREATE DATABASE hatchet;"
```

```bash
docker volume rm telejects_hatchet_config
```

```bash
make up hatchet-token
```

Then restart `make api` and `make worker`, so they pick up the new token.

## Checks

```bash
make test
```

```bash
make check
```

## Multi-tenancy

Every row belongs to a company (a realm) and every request works inside one company the user is
an active member of. Querysets refuse to run unscoped, and
`backend/apps/realms/test_isolation.py` proves isolation per endpoint and fails when a new route,
model or cross-company query skips the pattern.

## Secrets

Nothing sensitive is committed, ever: no passwords, tokens, keys or env values. Every
environment value lives in the gitignored `.env` that `scripts/init_env.sh` generates. See
[CLAUDE.md](CLAUDE.md) for the rules.
