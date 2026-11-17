# Telejects

What the product does is still to be specified: the specs in `specs/` will say. For now the app is
a sign-in and an empty dashboard on the same stack and process as eden-tracker.

The [README](README.md) covers setup and commands; read it first. These are the rules that aren't
obvious from the code. `backend/CLAUDE.md` and `frontend/CLAUDE.md` hold each side's rules.

## Architecture (do not drift without discussing first)

| Concern | Use | Never use instead |
|---|---|---|
| Frontend tooling | Vite+ (`vp`), pnpm | raw `npm i`, separate eslint/prettier |
| Routing | TanStack Router, one folder per screen under `frontend/src/routes/` | react-router |
| Server state | TanStack Query | Zustand or component state for API data |
| Client state | Zustand (tokens, UI filters) | context for global state |
| UI | shadcn (`frontend/src/components/ui`, vendored) + Tailwind v4 | other component libraries |
| API | Django + DRF + SimpleJWT, served over ASGI (Daphne) | WSGI servers |
| Live updates | Django Channels websocket, events over Postgres `LISTEN`/`NOTIFY` | Redis, polling as the main mechanism, data over the socket |
| Python tooling | uv (`uv add`, `uv run`) | pip, poetry |
| Background work, cron | Hatchet, on the same Postgres server | Celery, RQ, threads |
| Database | Postgres | |

## Secrets: nothing sensitive in the repo, ever

- No secret, password, token, key, real address or env value is committed, at any point, in any
  file: not in code, Compose files, tests, docs, fixtures, examples or commit messages. There is
  no `.env.example` with values in it either.
- Every environment value lives in the gitignored root `.env`, which `scripts/init_env.sh` creates
  with random secrets. Compose and Django both read that one file. A new setting gets a line in
  that script (a generated value, or an empty one) and is read through `env(...)` in settings.
- Settings have no fallback for secrets. A missing `DJANGO_SECRET_KEY` must fail, not default.
- Never print `.env` or read it into a conversation. To check a value, test for its presence or
  compare hashes.
- Real customer data is as sensitive as secrets. Test fixtures are invented data only; real
  samples Ruan shares stay outside the repo (or in a gitignored folder).
- Before any commit, read the staged diff for secrets and real data.

## Branches

- Work on `dev`. Never commit, merge or push to `main` unless Ruan asks.
- Commit only when asked.

## Access

- Every `/api/` route needs a signed-in user by default (`IsAuthenticated` in settings). A route
  that works before sign-in sets its own permission class and is listed, with a reason, in
  `backend/apps/core/test_access.py`. Don't extend that list to make a test pass.
- Multi-tenancy is not decided yet. If the specs call for shared workspaces (as eden-tracker's
  realms), raise it before the first domain model: it has to be in from the start, with
  isolation tests per endpoint.

## Local ports

Fixed, and offset from eden-tracker's so both run side by side: API 8010, web 5184, Postgres
5436, Hatchet dashboard 8892, Hatchet gRPC 7081. `make api` and `make web` take their port over
from whatever holds it, so check whether Ruan already has them running before starting your own,
and stop whatever you start (`make stop`) before finishing.

## Spec-driven workflow

Specs live in `specs/` (see `specs/README.md`). Ruan writes or approves a spec; then it is built.

A spec is done when, in the same change:
1. Every scenario has a passing test named `test_at_<spec>_<nn>_<what>`.
2. Every new endpoint is covered by the access tests, and `make test` and `make check` pass.
3. The spec's status is `Done` and its implementation notes are filled in.
4. `specs/README.md` is updated, and the CLAUDE.md files if a rule changed.

If a spec conflicts with the architecture table or these rules, stop and raise it first.

## Checking work

- `make test` needs the dev Postgres from `make up`. `make check` runs lint, formatting and types.
- Check UI changes in the running app, in both themes and at phone width.
- Run new Hatchet behaviour against a real local worker.
- Say plainly what wasn't tested, and don't report an inferred cause as fact.
