# Telejects

A project management platform for telecoms work ("tele-projects"). The specs in `specs/` build
it up; for now the app is a sign-in and an empty dashboard on the same stack and process as
eden-tracker.

Planned first specs:
- **0001 User management.**
- **0002 My settings** (changing my password).
- **0003 Integrations**, starting with feasibilities: a recreated and improved version of the
  feasibilities feature in Rapid (`~/SDXWorkspace/Rapid/connect-rapid`). Network providers (MTN,
  Vodacom, ...) each have their own feasibility API, products and way of querying. The plan is a
  connector layer in the style of primer.io: our side defines what a feasibility needs (a name,
  a lat/lon, the products wanted, ...) and each provider's connector maps its API onto that. The
  architecture is to be discussed with Ruan before 0003 is written: don't design it alone.
- **Later: client API access.** An Integrations section where a company creates API clients and
  works with a public, versioned API directly, feasibilities first. OAuth2 client credentials
  through django-oauth-toolkit: each API client belongs to a realm, its scopes are our
  permission codes (optionally limited to projects), and its secret is stored hashed.
- **Later: SSO and MFA** through django-allauth (OIDC and SAML), configured per company.
- **Later: per-project guest access** (see Multi-tenancy).

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

## Multi-tenancy: the rule that matters most

Telejects serves many companies. A realm is a company using the platform, and it runs many
projects inside it. Every piece of data belongs to one company (a realm in code),
and a user only ever sees or changes companies they are an active member of. A leak across
companies is the worst bug this system can have.

- Tenancy lives in its own platform app, `apps/realms` (spec 0001). The roles and permission
  codes are in `apps/realms/access_control.py`; companies are created by platform staff with
  `manage.py create_company`.
- **Company filtering lives on the queryset managers.** Every tenant model's manager is built on
  `TenantQuerySet` (`apps/realms/querysets.py`) and each app's queryset extends it, so the
  company is the first link of every query: `Project.objects.in_realm(realm).open()`
  (`in_realm_id(id)` in Hatchet tasks). A tenant queryset evaluated without `in_realm` raises
  `UnscopedQuery`; platform-wide uses call `.across_realms()` and every call site is
  allowlisted with a reason in `test_isolation.py`. Domain query methods never take a realm themselves; never filter on `realm=` by hand
  in views or services.
- New domain models subclass `TenantModel`. Viewsets extend `RealmScopedViewSet` and serializers
  `RealmScopedSerializer`. Names unique per company go in a per-realm constraint, never
  `unique=True`.
- `InRealm` is a default permission class. It resolves the company from the `X-Realm` header,
  refuses non-members, and sets `request.realm` and `request.membership`. Function views and
  custom actions filter by `request.realm` themselves.
- **Access is by permission, never by role name.** Permission codes live in one registry
  (`apps/realms/access_control.py`); views use `HasRealmPermission("<code>")`, code uses
  `request.membership.has_perm(code)`, the frontend `usePermission(code)`. A spec that adds a
  capability adds its codes and says which built-in roles get them. Roles are per-company rows
  (built-in ones read their permissions from code), so custom roles can come later.
- An endpoint that works across companies, or before sign-in, opts out explicitly and is added
  to the allowlist in `apps/realms/test_isolation.py` with a reason.
- **Every endpoint gets isolation tests in the same change**, in `apps/realms/test_isolation.py`:
  1. another company's rows stay out of lists, counts and aggregates;
  2. detail routes and custom actions on another company's rows return 404, for every method,
     and the row is unchanged afterwards;
  3. foreign keys in a request body can't point into another company;
  4. a non-member sending that company's `X-Realm` gets 403;
  5. permission limits hold (someone without a permission can't do what it allows).
- Two guard tests fail when the pattern is skipped: every `/api/` route must be company-gated or
  allowlisted, and every model in `apps/` must be a `TenantModel` or allowlisted. Don't extend
  an allowlist to make a test pass; fix the endpoint or model.
- Hatchet tasks run outside a request, so they take a `realm_id` and filter by it. File storage
  paths include the realm id.
- A websocket admits only an active member of the company it names and only ever says "this
  kind of data changed". It never carries data, so access is decided in one place, the API.
- Connectors (spec 0003) are no exception: provider credentials, requests and results belong to
  a company.
- **Per-project access is coming** (board-based, like monday.com): a guest from outside, such as
  a customer following their own project, sees only the projects granted to them. Belonging to
  a realm will not mean seeing all its projects. Once projects exist, every project-owned query
  chains `visible_to(membership)` after `in_realm`, and the isolation tests add a sixth check:
  a guest sees only their granted projects. Don't write code that assumes a member sees
  everything in the company.
- An endpoint is not done until its isolation tests pass.

## Local ports

Fixed, and offset from eden-tracker's so both run side by side: API 8010, web 5184, Postgres
5436, Hatchet dashboard 8892, Hatchet gRPC 7081. `make api` and `make web` take their port over
from whatever holds it, so check whether Ruan already has them running before starting your own,
and stop whatever you start (`make stop`) before finishing.

## Spec-driven workflow

Specs live in `specs/` (see `specs/README.md`). Ruan writes or approves a spec; then it is built.

A spec is done when, in the same change:
1. Every scenario has a passing test named `test_at_<spec>_<nn>_<what>`.
2. Every new endpoint has its isolation tests, and `make test` and `make check` pass.
3. The spec's status is `Done` and its implementation notes are filled in.
4. `specs/README.md` is updated, and the CLAUDE.md files if a rule changed.

If a spec conflicts with the architecture table or these rules, stop and raise it first.

## Checking work

- `make test` needs the dev Postgres from `make up`. `make check` runs lint, formatting and types.
- Check UI changes in the running app, in both themes and at phone width.
- Run new Hatchet behaviour against a real local worker.
- Say plainly what wasn't tested, and don't report an inferred cause as fact.
