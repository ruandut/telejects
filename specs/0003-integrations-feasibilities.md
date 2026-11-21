# 0003 — Integrations and bulk feasibilities

- **Status:** Done
- **Depends on:** 0001
- **Django apps:** new `integrations` (connectors, a company's connections, provider products,
  the engine that talks to providers); new `feasibilities` (runs, sites, results)
- **Touches:** frontend / backend / jobs / infra (an encryption key in `.env`, the first
  websocket consumer)

## Why
Telecoms projects start with "can we get a line to these sites, and from whom?". Companies have
accounts with network providers (MTN, Vodacom, Herotel, Link Africa, ...) and each provider has
its own feasibility API, product list and way of answering. Today, in Rapid, every provider is
hand-written Python, the answers are squeezed into a yes/no, results are shared between
companies and overwritten by later runs, and provider errors disappear.

Telejects puts one abstraction between the app and the providers, in the style of primer.io: we
define what a feasibility is (a site at a lat/lon, the products wanted) and what an answer looks
like, and each provider is described by a **connector definition**, data rather than code, that
maps its API onto ours. Adding a provider, or keeping its products fresh, should need no code.

The first use is the one Rapid's users rely on most: a list of sites from a spreadsheet, checked
against the providers and products the company picks, with the results exported.

## Scope
- In:
  - **The connector framework.** Connector definitions (auth, the fields a company fills in,
    operations, how answers map onto ours, schedules), run by one HTTP engine. A Python escape
    hatch behind the same interface for a provider that can't be described as data.
  - **An Integrations section** where a company sees the available connectors, connects its own
    provider accounts (a form built from the definition), tests the connection, and sees the
    provider's products and the last syncs.
  - **Workflows that keep integrations healthy**: product catalogue sync and a credential check,
    declared per connector and run on a schedule by Hatchet.
  - **Bulk feasibility runs from a CSV**: upload, map the columns, pick products, run on Hatchet,
    watch progress live, see per-site results, retry failures, cancel, export.
  - **Connectors:** Demo (no provider, for development and trying the flow), MTN and Vodacom.
  - The engine supports what Herotel and Link Africa need (GET requests, a key in a header or the
    query string, "present in the answer means feasible"), so they arrive as definitions only.
- Out (later specs):
  - Herotel and Link Africa definitions (next, definitions only).
  - Single-site feasibility from a map.
  - Pricebook and quotes (Rapid's `ConnectProduct` and price definitions).
  - Editing connector definitions in the portal. Platform staff author them for now.
  - Provider callbacks or webhooks (Vodacom's `callingBackUrl` isn't used).
  - Linking a run to a project, and project-level visibility (needs projects).
  - The public API for API clients. This spec's run endpoint takes JSON rows so it can be exposed
    later unchanged.
  - Reusing one company's earlier results to skip provider calls (no cache in 0003).

## Design notes

### What we learnt from Rapid
`connect-rapid/connect/interfaces/feasibilities/` has four providers:

| Provider | Request | Auth | Answer |
|---|---|---|---|
| MTN | POST, many sites per call (`inputs[]`) and product names | `X-API-KEY` header; also a requestor email and customer name | per site, per product: `product_feasible` yes/no and a capacity |
| Vodacom (AfriGIS) | POST, one site, product ids | `AuthKey` in the body | per product, per **access medium**: `feasible`, `coverage`, `status`, bandwidth groupings. For a fixed list of medium ids, coverage alone counts |
| Link Africa | GET, one site, bandwidth and term | key in the query string | `feasible`, products, bandwidth |
| Herotel | GET, one site | `api-key` header | a list of map keys present: on-net, near-net (needs a build), wireless coverage (needs an RF planner) |

What we keep: per-run sites with their line numbers and original columns, a column mapping step,
progress counts, cancel, re-queue, a CSV export with a column per product. What we fix: no
results shared across companies, nothing overwritten, every provider error recorded against the
site, credentials per company and encrypted, more than yes/no, MTN's batching used, provider
limits respected, no hard-coded provider ids or name maps in code.

### The canonical model (our side of the abstraction)
Everything outside the engine (services, tasks, the API, the UI, the export) uses only these:

- **`SiteQuery`**: `ref` (our site id), `name`, `latitude`, `longitude`, optional
  `bandwidth_mbps`, optional `term_months`.
- **`ProductType`**: a fixed system list, `fibre`, `fixed_wireless`, `lte`, `5g`, `microwave`,
  `satellite`, `other`. Every provider product maps to one, so results read across providers and
  code and jobs reason about types, not provider names.
- **`FeasibilityAnswer`** per site × provider product (× variant, such as Vodacom's access
  medium): a **status** of `available`, `near_net` (needs a build), `coverage_only` (in coverage,
  needs planning or a survey), `not_available`; bandwidth ranges in Mbps; a short provider note.
- **`ConnectorError`**: `auth`, `rate_limited`, `timeout`, `provider_down`, `bad_request`,
  `bad_response`, each retryable or not.

Users pick **provider products**; the product type is the system abstraction under them.

### Connector definitions (the provider's side)
A definition is a versioned JSON document, validated against a schema (Pydantic). It holds:

- **Identity:** key (`mtn`), name, logo, the capabilities it offers (`feasibility`).
- **Base URL:** https only, fixed in the definition. A company never supplies a URL.
- **Connection fields:** what a company fills in, each with a label, help text, type, required,
  and whether it is **secret** (e.g. MTN: API key (secret), requestor email, customer name).
- **Auth:** where secrets go: a header, a body field or a query parameter (OAuth2 client
  credentials can be added later as another kind).
- **Operations:** `list_products`, `check_feasibility` and `test_connection` (which may point at
  `list_products`). Each has a method, path, a request template, how many sites one call takes
  (MTN many, others 1), timeout, retries on which errors, and the provider's rate limit.
- **Request templates** are JSON with placeholders for the call context (`site.latitude`,
  `products[].code`, `connection.requestor_email`, ...). No Jinja, no `eval`, no code: a
  definition can only put context values into a fixed structure.
- **Response mapping** reads answers with JMESPath expressions into the canonical model: where
  the sites are, which product and variant each answer is for, and **status rules** in order
  (e.g. Vodacom: `feasible && coverage && status == "complete"` → `available`; coverage only →
  `coverage_only`, except the listed medium ids, where coverage → `available`; else
  `not_available`. Herotel: key present → the mapped status; absent → `not_available`).
- **Product mapping:** how `list_products` answers become provider products (code, name,
  variant), and rules from name, category or variant to a `ProductType`.
- **Error mapping:** HTTP status and answer patterns to `ConnectorError` kinds.
- **Schedules:** which operations run on their own and how often (catalogue sync daily, credential
  check hourly).

**Authoring.** Platform staff write definitions. The built-in ones live in the repo as JSON under
`apps/integrations/definitions/` and `manage.py load_connectors` loads them; staff can also add or
edit them in Django admin. A saved version is immutable; a change is a new version. Connections
use the latest published version, and every provider call records the version it used.

**Escape hatch.** A definition can name a Python connector class instead of operations, for a
provider that needs signing, polling or SOAP. It implements the same interface and returns the
same canonical model. None of 0003's connectors need it; it exists so the abstraction never has
to bend.

**Safety.** Requests only go to the definition's base URL. Secrets are put only where the auth
block says, and are never logged, never stored in recorded requests (redacted), never returned
by the API. Raw answers are stored for debugging and re-mapping.

### Data model
`integrations`:
- **`ConnectorDefinition`** (platform data, not a `TenantModel`: one catalogue for every company,
  read-only to them; allowlisted in the model guard test with that reason): key, version, spec
  JSON, published, created by.
- **`Connection`** (`TenantModel`): a company's account with a provider. Name (unique per
  company; a company may have two MTN accounts), definition key, settings (non-secret fields),
  secrets encrypted with Fernet (`cryptography`, a `MultiFernet` key list for rotation, from
  `INTEGRATIONS_ENCRYPTION_KEYS` in `.env`, generated by `init_env.sh`, no fallback), enabled,
  health (`ok`, `failing`, `unknown`) with the last error and when it was checked.
- **`ProviderProduct`** (`TenantModel`): synced per connection. Code, name, variant, product type,
  raw, `retired_at` (a product the provider stops returning is retired, never deleted, because
  past results point at it; retired products can't be picked for new runs).
- **`SyncRun`** (`TenantModel`): one scheduled or manual operation on a connection: kind, started,
  finished, outcome, counts (added, retired), error.

`feasibilities`:
- **`FeasibilityRun`** (`TenantModel`): name, created by, status (`queued`, `running`,
  `completed`, `cancelled`), the picked products, the column mapping, the original column names,
  counts, started and finished.
- **`RunSite`** (`TenantModel`): run, line number, name, latitude, longitude, the row's other
  columns (JSON, for the export).
- **`ProviderCheck`** (`TenantModel`): one call's worth of work, a set of coordinates × a
  connection. Status (`pending`, `done`, `failed`, `cancelled`), attempts, error kind and message,
  definition version, duration, raw answer.
- **`FeasibilityResult`** (`TenantModel`): run site, provider product, variant, status,
  bandwidths, note. Written once; a run's results never change after it completes. Only what can
  be delivered is stored (available, near-net, coverage only): an answered site with no result
  for a product reads as "Not available" (decided by Ruan after the live Vodacom run, where each
  product came back with ~20 access media, most of them not feasible).

The same coordinates appearing twice in a run are checked once and the answer applies to both
sites.

### Hatchet
- `run-feasibility` (`realm_id`, `run_id`): creates the checks, grouping sites per connection into
  calls of the definition's size, and spawns a child per call.
- `check-feasibility-batch` (`realm_id`, `run_id`, `check_id`): one provider call through the
  engine. Hatchet **concurrency keyed by connection** and a **rate limit per connection** from the
  definition, so a big run never floods a provider. Retries with backoff only for retryable
  errors; the last failure is recorded on the check and the run carries on.
- The parent finishes the run when every check is done or failed, or stops when cancelled
  (cancelling marks pending checks `cancelled` and cancels their Hatchet runs).
- `sync-connection` (`realm_id`, `connection_id`, `operation`): a catalogue sync or credential
  check. Run on connect, from a button, and by a static hourly cron, `integrations-due`, which
  finds connections due an operation by their definition's schedules (its query is cross-company,
  so it is allowlisted with that reason) and spawns one task per connection with its `realm_id`.
- An `auth` error marks the connection `failing`; its pending checks fail with "The provider
  refused this connection's credentials" rather than retrying.

### Live progress and results
Results appear line by line while a run is going, not when it finishes. Rapid builds the results
only at the end (`process_gen_csv`); here each `check-feasibility-batch` writes its sites'
`FeasibilityResult` rows and updates the run's counts in the same transaction as it completes, so
the API always shows every finished line.

The first websocket consumer pushes those lines to the UI as they finish, under the same access
rules as the API:
- **Who can connect.** The socket authenticates with a JWT as its first message and names a
  company; only an active member gets in. Subscribing to a run needs `feasibilities.view`;
  subscribing to integrations needs `integrations.view`. A run of another company is refused as
  if it doesn't exist.
- **How a line gets there.** When a check commits, the task sends `NOTIFY` with the realm id, the
  run id and the changed site ids (ids only: `NOTIFY` is capped at 8 KB and isn't
  access-checked). The consumer loads those sites with the same scoped queryset
  (`RunSite.objects.in_realm(realm)`, later `.visible_to(membership)`) and the same serializer as
  `GET .../runs/<id>/sites/`, and sends each subscriber the lines and the run's counts. The UI
  writes them straight into its TanStack Query cache, so the table fills in as you watch.
- **Access is rechecked before sending**, so someone removed from the company, or whose role
  loses `feasibilities.view`, stops receiving on the next event.
- **Coalesced:** at most about one message a second per run, carrying every line that finished
  in that second, so a run of thousands of sites doesn't flood the socket.
- **Nothing is lost:** on reconnect, the UI refetches the run and the page it shows through the
  API, then carries on from the socket.
- Connections get the same treatment: a health change or finished sync is pushed to subscribers
  with `integrations.view`, serialized as the API does (never with secrets).

Ported from eden-tracker's pattern (JWT as the first message, Postgres `LISTEN`/`NOTIFY`).

### API
All realm-scoped, under `/api/integrations/` and `/api/feasibilities/`:
- Connectors: list the published catalogue (latest version of each).
- Connections: list, create (definition key, name, fields), update (fields; a secret is replaced
  only when sent, and is shown back only as "set"), delete (disables if runs used it), `test`,
  `sync`.
- Products: list per connection, filter by type and retired.
- Runs: list, create (name, product ids, column mapping, rows as JSON with line numbers, so the
  browser parses the file and the later public API can post the same body), detail with counts,
  `cancel`, `pause` and `resume` (a running run stops starting calls, then carries on),
  `retry-failed` (re-queues only failed checks), `rerun` (checks a finished run's sites
  again, replacing its results), sites with results (paged, filter by
  status, or `?ids=` for the sites a live event named), `export` (CSV; for a run still going, the
  lines finished so far, the rest marked "Pending").

Limits (drafted, see Decisions): 10,000 rows per run; name 1–100 characters; latitude −90..90,
longitude −180..180.

### Portal
- **Integrations** (`/integrations`): the connectors, each "Connect" or its connections with
  health. A connection page: the generated settings form, Test connection, products grouped by
  type, sync history, Sync now.
- **Feasibilities** (`/feasibilities`): runs with status and progress. **New run:** upload a CSV
  or XLSX, map name, latitude and longitude (optionally bandwidth), see the rows that will be
  left out and why, pick products grouped by provider and filterable by type, start. **A run:**
  live progress, a table of sites with a status per product, errors per site, Pause and
  Continue, Cancel, Retry failed, Run again (asks first, in a dialog), Export.
- The export keeps the uploaded columns in order, then a column per picked product ("Available",
  "Near-net", "Coverage only", "Not available", "Error"), then an "Errors" column.

### Who may do what
New permission codes in `access_control.py`:

| Code | Lets someone | Admin | Project manager | Viewer |
|---|---|---|---|---|
| `integrations.view` | See connectors, connections (never secrets) and products | ✓ | ✓ | |
| `integrations.manage` | Connect, edit, test, sync and remove connections | ✓ | | |
| `feasibilities.view` | See runs, results and export | ✓ | ✓ | ✓ |
| `feasibilities.run` | Start, pause, continue, cancel, retry and run again | ✓ | ✓ | |

Starting a run needs `feasibilities.run` only; the product picker lists the company's products
without needing `integrations.view`.

### Designed for later
- **Projects:** a run gets an optional project; project-owned queries chain
  `visible_to(membership)` and a guest sees only runs of their granted projects. Until then runs
  are company-level, seen with `feasibilities.view`.
- **Single site from a map:** the same engine and canonical model, one site, run inline with a
  short timeout or as a one-site run.
- **Public API:** the run create body is already JSON rows; API clients get `feasibilities.*`
  scopes.
- **Pricebook:** maps provider products (or product types) to a company's own offerings and
  prices.

### Testing
- Each definition is tested against recorded answers (invented sites and data, never real
  customer data) with HTTP mocked; `make test` makes no provider calls.
- Engine tests cover GET and POST, auth in header, body and query, batching, status rules, error
  mapping and secret redaction, so Herotel and Link Africa need only definitions.
- `manage.py check_connection <id>` runs a live `test_connection` against a configured connection,
  for staff with real credentials.
- New dependencies: `httpx`, `jmespath`, `cryptography`; `respx` for tests.

## Scenarios

### Integrations

### AT-0003-01 — I see the providers I can connect
- Given I have `integrations.view`
- When I open Integrations
- Then I see each available connector with its name and what it offers, and the company's
  connections with their health

### AT-0003-02 — I connect a provider by filling in what it asks for
- Given I'm an Admin
- When I connect MTN, filling in the fields its connector asks for (API key, requestor email,
  customer name), and save
- Then the connection is tested, shows "Connected", and its products appear grouped by type

### AT-0003-03 — Wrong credentials are caught when I connect
- When the provider refuses the credentials I gave
- Then I see "The provider refused this connection's credentials", the connection shows as
  failing, and no products are synced

### AT-0003-04 — Secrets never come back
- Given a connection with an API key
- When anyone opens or lists it, or reads its sync history or a run's recorded calls
- Then the key shows only as "set", and appears in no response or log
- And I can replace it, and leaving it empty keeps the old one

### AT-0003-05 — Products are kept fresh
- Given a connection whose catalogue sync is due
- When the scheduled sync runs and the provider has added one product and dropped another
- Then the new product is listed, the dropped one is marked retired and can't be picked for new
  runs, and earlier results that used it still show it
- And the sync shows in the connection's history with what changed

### AT-0003-06 — A failing connection is flagged
- When the scheduled credential check is refused by the provider
- Then the connection shows "Failing" with the reason, on its page and in the Integrations list

### AT-0003-07 — Only Admins manage integrations
- Given I'm a Project manager
- Then I can see connections and products but can't connect, edit, test, sync or remove one
- And a Viewer can't see Integrations at all

### AT-0003-08 — A new connector needs no code
- Given platform staff load a new connector definition
- Then companies see it in Integrations and can connect it, with no deploy
- And an invalid definition is refused with what's wrong

### Running feasibilities

### AT-0003-09 — I check a list of sites from a CSV
- Given my company has MTN and Vodacom connected
- When I upload a CSV, map the name, latitude and longitude columns, pick products from both, and
  start the run
- Then I see the run with its progress, and when it's done each site has a status per product:
  Available, Near-net, Coverage only or Not available

### AT-0003-10 — Bad rows are shown before I start
- When my file has rows with no name, a latitude outside −90..90, a longitude outside −180..180,
  or coordinates that aren't numbers
- Then I see those rows with their line numbers and why, before I start
- And the run checks only the good rows

### AT-0003-11 — I see each line's results as it finishes
- Given a run is going and I have it open
- When a provider answers for some sites
- Then those lines show their status per product straight away, and the run's progress counts
  move, without reloading the page
- And lines still waiting show "Pending"

### AT-0003-12 — The live socket shows only what the API would
- Given a run is going
- Then the lines pushed to me are exactly what the API returns for them, in the same shape
- And someone who isn't an active member of the company can't connect for it, someone without
  `feasibilities.view` can't subscribe to its runs, and a run of another company is refused
- And if I'm removed from the company or lose `feasibilities.view` while watching, I stop
  receiving lines

### AT-0003-13 — Nothing is lost if the connection drops
- Given my connection drops while a run is going
- When it reconnects
- Then the lines that finished meanwhile show their results

### AT-0003-14 — One provider failing doesn't stop the run
- Given Vodacom times out for some sites, even after retries
- Then the run completes, those sites show "Error" for Vodacom products with the reason, and
  their MTN results are there

### AT-0003-15 — I retry only what failed
- Given a completed run with failed checks
- When I choose Retry failed
- Then only the failed checks are sent again, and the sites that succeeded keep their results

### AT-0003-16 — I cancel a run
- When I cancel a running run
- Then no more provider calls are made, it shows "Cancelled", and results so far are kept

### AT-0003-17 — The export keeps my spreadsheet
- When I export a completed run
- Then I get a CSV with my uploaded columns in their order, a column per picked product with its
  status, and an Errors column

### AT-0003-18 — Providers are respected
- Given a run of hundreds of sites
- Then MTN is sent many sites per call, every provider stays within its connector's concurrency
  and rate limits, and a site at the same coordinates as another is checked once

### AT-0003-19 — Results don't change after a run
- Given a completed run
- When a later run checks the same sites, or a product is retired
- Then the first run's results are unchanged (only running that run again replaces them, 28)

### AT-0003-20 — Refused credentials don't keep retrying
- Given a connection's credentials stop working mid-run
- Then its remaining checks fail with "The provider refused this connection's credentials", the
  connection shows as failing, and other providers carry on

### AT-0003-21 — Who can run and see feasibilities
- Given I'm a Viewer, I can see runs and results and export them, but can't start, cancel or
  retry one
- And someone with neither feasibility permission sees no Feasibilities section and gets 403
  from its API

### AT-0003-28 — I run a run again
- Given a completed or cancelled run
- When I choose Run again and confirm
- Then all its sites are checked again against the products it picked that are still offered,
  and its old checks and results are replaced by the new ones (the run keeps its id, name and
  sites)
- And a run still going, one with a provider call still finishing after a cancel, or one whose
  products are all retired can't be run again

### AT-0003-29 — I rename a run
- Given a run, whether it is still going or finished
- When I rename it
- Then the new name shows on the run, in the list and in open tabs, and the export is named after
  it; nothing else about the run changes
- And a name can't be blank or longer than 100 characters, and a Viewer can't rename a run

### AT-0003-30 — I pause a run and continue it
- Given a running run
- When I pause it
- Then it shows "Paused", no new provider calls start for it (calls under way finish), and my
  company's other runs carry on
- When I choose Continue
- Then its remaining sites are checked, after the other runs my company has going, and it
  completes
- And a paused run can be cancelled but not run again, and a Viewer can't pause or continue one

### AT-0003-31 — Companies take turns on a shared account
- Given several companies run feasibilities at once on one provider account (such as one of
  Telejects' accounts)
- Then they take turns within that account's limits, so each sees progress; a busy company
  slows the others down but never holds them up
- And within one company, runs go in the order they started (pause one to let another go first)

### AT-0003-32 — I change a run's products
- Given a completed or cancelled run
- When I choose Edit products, the dialog tells me saving runs it again, and I save new picks
- Then the run's products are replaced by the new ones, and all its sites are checked again
  against them, replacing its old checks and results (the run keeps its id, name and sites)
- And I must pick at least one product, each one my company's connections still offer; another
  company's products are refused (AT-0003-26); the same runs as AT-0003-28 can't be changed

### Connectors

### AT-0003-22 — MTN's answers become ours
- Given recorded MTN answers for invented sites
- Then each product's yes/no and capacity map to Available or Not available with its bandwidth,
  sites are matched back by their position in the batch, and an MTN error becomes the right error
  kind

### AT-0003-23 — Vodacom's answers become ours
- Given recorded Vodacom answers
- Then each access medium is its own result, `feasible`, `coverage` and `status` follow the
  definition's rules, and bandwidth
  groupings become ranges

### AT-0003-24 — The Demo connector works without a provider
- Given the Demo connector is enabled (development and staging only)
- When I connect it and run feasibilities
- Then I get predictable results from the coordinates, including some errors, with no provider
  called

### Keeping companies apart

### AT-0003-25 — Another company's integrations and runs stay out of sight
- Given another company has connections, products, runs and results
- Then none appear in my lists, counts or exports, and their detail routes and actions (test,
  sync, cancel, retry, export) return 404 and change nothing

### AT-0003-26 — A run can't use another company's products
- When I start a run naming a product synced for another company's connection
- Then it is refused, and nothing is sent to any provider

### AT-0003-27 — Tasks stay in their company
- Given two companies run feasibilities at the same time with the same provider
- Then each run's checks use only its own company's connection and credentials, and write only
  its own results

## Decisions
Decided with Ruan:
1. **Connector definitions** are written by platform staff, versioned and global; companies only
   connect them.
2. **Credentials:** each company brings its own provider accounts. Nothing is shared across
   companies.
3. **Products:** users pick provider products; a system product type sits under every provider
   product so code and jobs work with one shape.
4. **0003 scope:** framework, Integrations section, Demo, MTN and Vodacom, bulk CSV runs.
   Herotel and Link Africa next, then single-site from a map.
5. **Provider callbacks** are out; they aren't used.

Open until Ruan approves the spec:
6. **Definitions as data.** Drafted: JSON validated by a schema, JMESPath for reading answers,
   placeholder templates for requests, a Python class as escape hatch. Worth confirming that
   "no code" means "no code for providers that fit", not "never".
7. **Where definitions are edited.** Drafted: JSON in the repo for built-ins, loaded by command,
   plus Django admin. A portal editor for platform staff later.
8. **Definition versions.** Drafted: connections follow the latest published version; each call
   records the version. Alternative: connections pin a version and are upgraded explicitly.
9. **Run limits.** Drafted: 10,000 rows per run. Rapid has none.
10. **Status words.** Drafted: Available, Near-net, Coverage only, Not available. Rapid shows
    Vodacom's coverage-without-feasible as not feasible; here it becomes Coverage only.
11. **XLSX.** Drafted in (parsed in the browser, as Rapid does). Could be CSV only at first.
12. **Demo connector** visible only where `INTEGRATIONS_DEMO_ENABLED` is set.
13. **Live line results over the socket.** Decided with Ruan: results show per line as the run
    goes, and the socket carries them. The rule "the socket never carries data" is replaced in
    CLAUDE.md by "the socket is held to the API's rules": same authentication, membership,
    permission codes and scoped querysets and serializers, rechecked before sending, with
    isolation tests per consumer.

## Implementation notes

Built as approved, with decisions 6–12 as drafted and 13 as decided.

- **Connector framework (`backend/apps/integrations/`):**
  - `canonical.py`: the canonical model (`SiteQuery`, `ProductType`, `Status`, `Answer`,
    `ConnectorError` with kinds and retryability).
  - `spec.py`: the definition schema (Pydantic; https-only base URL, expressions compiled on
    load, Python connectors only under `apps.integrations.connectors`).
  - `templating.py`: request templates, dotted lookups only.
  - `engine.py`: runs a definition over httpx, with JMESPath (plus `lower`/`upper`) for
    reading answers. It handles batches matched by position, per-variant answers (`variants`,
    added for Vodacom's access media), auth in a header, body or query, error rules, and
    redaction of secrets in every recorded call.
  - `definitions/`: `demo.json` (the Python escape hatch, `connectors/demo.py`), `mtn.json`
    (batches of 20) and `vodacom.json`. Rapid's workaround (coverage alone counts as available
    for a fixed list of access media) was a status rule in v1; Ruan turned it off in v2
    (2026-11-17) until it's looked into again.
    `manage.py load_connectors` (also run by `make migrate`) saves a changed one as a new
    version; `manage.py check_connection <realm> <connection>` tests one live.
  - `crypto.py`: Fernet secrets from `INTEGRATIONS_ENCRYPTION_KEYS` (`init_env.sh` writes it,
    and appends it to an existing `.env`).
  - `services.py`: connect, update, remove (turns off a used connection), test, sync, the
    `connect` operation (test, then sync) and `due_operations`.
  - `tasks.py`: `integrations-run-operation` and the hourly `integrations-due` cron.
- **Runs (`backend/apps/feasibilities/`):**
  - `services.py`: `start_run` validates rows with the same messages the portal shows.
    `plan_run` (worker) makes one check per connection and batch of unique coordinates.
    `perform_check` calls the provider, retries retryable errors, writes results per line as it
    finishes and publishes the changed site ids.
  - Also in `services.py`: cancel and retry-failed. An `auth` error fails that connection's other
    pending checks and marks it failing.
  - `tasks.py`: `feasibility-check` has Hatchet concurrency keyed by connection (`max_runs` from
    the definition) and a dynamic rate limit per connection.
  - `views.py`: the API, plus the CSV export (formula-safe cells).
- **Live socket:**
  - `apps/realms/consumers.py`, `events.py`, `listener.py`, `live.py`, `routing.py`: ported
    from eden-tracker, then extended with topic subscriptions. Each app declares its topics in
    its own `live.py`, with a permission code, a scoped lookup and a renderer that uses the API's
    serializers (rendered with DRF's JSON renderer, so the bytes match).
  - Access is rechecked before every send.
  - `feasibility_run` pushes finished lines and counts. `feasibility_runs` and `integrations`
    only say "changed".
- **Portal (`frontend/src/`):**
  - `network/socket.ts`: one socket per tab, with subscriptions; the realm gate points it at the
    tab's company. `features/realms/live.ts` holds `useLive`.
  - `features/integrations/` and `routes/_app/integrations/`: catalogue, connect dialog, the
    form generated from the definition, products by type, history.
  - `features/feasibilities/` and `routes/_app/feasibilities/`: runs, a new run (CSV via
    papaparse, XLSX via read-excel-file, column mapping, bad rows by line, product picker), and
    a run page whose lines fill in from the socket, with filters, cancel, retry and export.
- **Permissions:** `integrations.view`, `integrations.manage`, `feasibilities.view` and
  `feasibilities.run`, granted as the table above says.
- **Tests:**
  - `apps/integrations/test_engine.py`: templating, definition validation, MTN (22), Vodacom
    (23), a presence-style provider needing only a definition, and Demo (24).
  - `apps/integrations/test_integrations.py`: 01–08.
  - `apps/feasibilities/test_feasibilities.py`: 09–11 and 14–21.
  - `apps/realms/test_isolation.py`: 25–27 and the socket tests (12, 13), including one through
    real Postgres `LISTEN`/`NOTIFY`.
  - Provider APIs are faked with respx (`conftest.py`), with invented data. Hatchet runs inline
    through the `worker` fixture.
- **Run again (AT-0003-28, added 2026-11-20 at Ruan's request):** `services.rerun` deletes
  the run's checks (results cascade), keeps only its still-current products, resets the counts
  and queues it for planning like a new run. Request logs keep the old calls; they name the
  run, so the run's Requests link shows every pass. Tests in `test_feasibilities.py` (28) and
  added to 21 and 25.
- **Rename (AT-0003-29, added 2026-11-21 at Ruan's request):** `PATCH
  /api/feasibilities/runs/<id>/` with `{"name"}` (`feasibilities.run`), through
  `services.rename_run`, which updates only the name (a run still going isn't raced) and
  publishes to the list and the run. The run page has a pencil by the name. Tests in
  `test_feasibilities.py` (29) and added to 21 and 25.
- **Pause and continue (AT-0003-30, added 2026-11-21 at Ruan's request):** a new `paused`
  status (counts as still going). `services.pause_run` leaves the checks pending; queued check
  tasks that reach a worker skip. `resume_run` queues the pending checks again, so they go
  behind the company's other runs. Tests in `test_feasibilities.py` (30) and added to 21 and 25.
- **Taking turns (AT-0003-31, added 2026-11-21):** `feasibility-check` has a second
  round-robin concurrency key, `limit_key:realm_id`, under the account's own key. Test 31
  checks the configuration; the scheduling itself is Hatchet's.
- **Dropping queued tasks:** each check task carries `feasibility_run: <realm>:<run>`
  metadata. Pausing and cancelling start `feasibility-drop-queued`, which cancels that run's
  tasks still queued in Hatchet from before that moment. Otherwise each would still take a turn
  and a unit of the account's rate limit from everyone on it.
- **Edit products (AT-0003-32, added 2026-11-21 at Ruan's request):** `POST
  /api/feasibilities/runs/<id>/rerun/` takes an optional `products` list; given, it is checked
  as when starting a run (`services._check_products`) and replaces the run's products before it
  runs again. The run page's Edit products dialog (`edit-products-dialog.tsx`) reuses the
  product picker and says saving runs it again. Tests in `test_feasibilities.py` (32) and added
  to 26.
- **Deviations:**
  - The planning task makes the checks, not the request, so starting a 10,000-row run returns
    quickly.
  - `ProviderCheck.connection` and `FeasibilityResult.product` are `RESTRICT`, not `PROTECT`:
    a used connection or product can't be deleted on its own, but deleting a company still works.
  - A Demo call fails when its first site is one of the deterministic failing ones (about 1 in
    13 calls), every time, so retrying it fails too.
- **Checked in the running app** (Ruan's API and web servers, plus a second worker of mine, in a
  throwaway company deleted afterwards):
  - connecting Demo (tested, products synced);
  - a new run from a CSV with three bad rows, which were listed by line;
  - lines filling in live from the socket (two site fetches for the whole run);
  - completion, Retry failed with lines updating live, and the export;
  - the run, new-run, list and connection pages in light and dark mode and at phone width.
- **Not checked live:**
  - The API's own enqueue to Hatchet. Ruan's running API process holds a Hatchet token from
    before today's reset ("invalid auth token"), so I enqueued from a shell with the current
    token. The tests cover the API path inline.
  - MTN and Vodacom against their real APIs (no credentials; recorded shapes only).
