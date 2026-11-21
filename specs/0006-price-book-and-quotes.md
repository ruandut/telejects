# 0006 — Telejects' price book and single-site quotes over the API

- **Status:** Done
- **Depends on:** 0001, 0003, 0004 (and 0005: every provider call is logged)
- **Django apps:** new `pricebook` (the platform price book, Rapid-compatible endpoints, exports);
  new `api_clients` (OAuth2 client credentials, a company's machine access); new `site_checks`
  (one-site checks); `integration_logs` (a `site_check_id` link)
- **Touches:** frontend / backend / jobs

## Why
Rapid's clients call two endpoints to check a site and price it: `single-site-feasibility`
(which provider products are feasible here) and `single-site-feasibility-quote` (what Skybird
would charge for them, from Skybird's price book). They are moving from Rapid to Telejects and
shouldn't have to rewrite their integrations. Telejects keeps Rapid's paths, request bodies and
JSON responses exactly; only the host changes, and how a client gets its token.

Rapid's price book is one global book, kept by Skybird staff. Telejects keeps it the same way:
one **platform price book**, kept by Telejects staff, in the style of 0004's platform accounts:
every company may quote from it from the start, and staff can limit it to granted companies.
Per-company price books come later.

## Scope
- In:
  - **The platform price book** in Django admin: provider products, Vodacom access media,
    price definitions and connect products, with Rapid's CSV import, CSV template, CSV export and
    the PDF price book. Offered to every company, unless staff limit it to granted ones.
  - **A one-time import from Rapid** (`manage.py import_rapid_pricebook <dump>`), keeping Rapid's
    ids for connect products, definitions, provider products and access media.
  - **API clients** (OAuth2 client credentials): a company's admin creates one in the portal,
    picks its permissions, and sees its secret once.
  - **The Rapid-compatible client endpoints**, same paths, bodies, responses and errors:
    `POST /api/single-site-feasibility/`, `POST /api/single-site-feasibility-quote/`,
    `GET /api/connect-product/` (list and detail) and `GET /api/product/` (list and detail).
  - **One-site checks** behind them, through the company's own connections (own or platform
    account), logged like every other provider call.
- Out (later specs):
  - Rapid's `/auth/token/`, `/auth/token/2fa/` and its integration accounts: clients switch to
    OAuth2 client credentials (decided: Ruan, 2026-11-17).
  - A portal screen for single-site checks and quotes; that is the "single site from a map" spec,
    which will reuse this one's services.
  - Price book editing in the portal (Rapid's pricebook admin pages and its
    `connect-product-definition`, `access-medium`, `sublayer-providers` and
    `generate-pricebook-*` endpoints). Those were Skybird staff tools; here staff use Django admin.
  - Per-company price books, margins on the platform book, formal quotes.
  - Quoting Link Africa and Herotel (Rapid doesn't either).
  - Rapid's location cache (`CACHE_ENABLED` is off in Rapid, so every call checks live).
  - A versioned public API. These Rapid paths are a compatibility layer, frozen as they are.

## Design notes

### The price book (platform data, not tenant data)
Copied from Rapid's `connect` models, with their ids. None are `TenantModel`s: like
`PlatformAccount`, they belong to Telejects, and each goes on the tenant-model allowlist with
that reason. Companies never write them; they read them only through the endpoints below, and
only when granted.

- **`CatalogueProduct`** (Rapid's `Product`): `id` (Rapid's), `name`, `provider` (Rapid's fixed
  numbers: 0 Vodacom, 1 MTN, 2 LINK_AFRICA, 3 Herotel), and what it means in Telejects:
  `connector` (definition slug) and `product_code`, matched against each company's
  `ProviderProduct` rows.
- **`AccessMedium`** (Vodacom's delivery method): `id` (Rapid's), `name`,
  `provider_access_medium_identifier_id`; it matches a Vodacom result's `variant_code`.
- **`PriceDefinition`** (Rapid's `ConnectProductDefinition`): every Rapid field, same names
  (including `none_recurring_cost`, and -1 meaning price on request), `sublayer`, and either an
  access medium (Vodacom) or a catalogue product.
- **`ConnectProduct`**: `id`, `name`, `description`, its price definitions.
- **`PriceBook`**: a name and `available_to_all` (on by default), as on `PlatformAccount`.
  One book, "Telejects", is made by a migration, and its connect products belong to it.
- **`PriceBookGrant`** (`TenantModel`): a company may quote from a book that isn't offered to
  all. Staff manage grants in Django admin, as with `PlatformGrant`.

Provider numbers are fixed constants, not rows, so `provider_id` 0–3 in responses never moves.
New providers get the next number.

### API clients
django-oauth-toolkit, client-credentials grant only, as CLAUDE.md planned.
- An `ApiClient` (`TenantModel`) is an OAuth application owned by one company, with a name, the
  member who made it, its permission codes (its scopes, a subset of its maker's), and its secret
  stored hashed. Its token is a bearer token on the same `Authorization` header Rapid used.
- `POST /api/oauth/token/` with `grant_type=client_credentials`, the client id and secret.
  Access tokens last 1 hour; clients ask for a new one (no refresh token).
- A request with an API client token works in that client's company: `InRealm` takes the
  company from the token and needs no `X-Realm` (Rapid clients never sent one; one that names
  another company gets 403). `request.membership.has_perm` answers from the client's scopes.
- Admins see and revoke their company's clients on the **API clients** page. A revoked client,
  or a maker who is removed or loses a permission, stops the token working (or doing that) at
  once.
- New permission code `api_clients.manage` (Admin only).

### The Rapid-compatible endpoints
Paths stay exactly as Rapid's under `/api/`. Permission codes: new **`feasibilities.quote`**
(Rapid's `can_quote_feasibilities`), Admin and Project manager. A company needs a
`PriceBookGrant` for anything that reads the price book.

| Endpoint | Needs | Response |
|---|---|---|
| `POST /api/single-site-feasibility/` | `feasibilities.run` | Rapid's `{success, exceptions, data}`; `data` items `{id, access_medium}` |
| `POST /api/single-site-feasibility-quote/` | `feasibilities.run`, `feasibilities.quote`, grant | Rapid's `{success, exceptions, notice, data}`; `data` items `{connect_product_name, connect_product_id, products: [{name, provider, provider_id, price_options}]}` |
| `GET /api/connect-product/` (`/<id>/`) | `feasibilities.quote`, grant | Rapid's page `{count, next, previous, results}` of `{name, id, description, products}` |
| `GET /api/product/` (`/<id>/`) | `feasibilities.run` | Rapid's page of `{id, provider_verbose: {id, name}, name, provider}` |

Rapid's details kept on purpose: page size 20 with `page` and `page_size`, search by
`search_string`; `timeout` between 5 and 50, default 50; validation errors in DRF's shape,
including Rapid's `{"connect_products": ["One or more connect_products are invalid."]}`; a failed
check returns 400 `{"error": "Failed to conduct feasibility: …"}`; prices as strings with two
decimals (`"-1.00"`); `provider` as Rapid's names (`"LINK_AFRICA"`); `provider_id` null on a
Vodacom definition without a product; the quote's grouping (Vodacom by access medium and name,
first; others by product); and every price option field Rapid sends (`id`, `duration`, both
costs, data allocation and notes, both bandwidths, `medium`, `product`, `access_medium`), which
is more than Rapid's docs show.

Each response is held to Rapid's response in a contract test, field for field, so drift fails
the build. The expected responses (`apps/pricebook/rapid_responses/`) are worked out from Rapid's
views and serializers with invented data, not recorded from a running Rapid.

**Ids in results.** `single-site-feasibility`'s `data[].id` was Rapid's `AvailableConnection`
id; here it is the id of the stored one-site result, unique and stable, though not Rapid's.

**Exceptions.** Each failed or skipped provider becomes `{"exception", "message"}`: the
connector's error kind as the name (`"Timeout"`, `"Auth"`) and its safe message. A provider the
company has no enabled connection for is reported as `{"exception": "NotConnected", …}`.

### One-site checks
- `SiteCheck` (`TenantModel`): who asked (member or API client), coordinates, the products asked
  for, timeout, outcome; its `SiteCheckResult` rows are the canonical answers (product, variant,
  status, bandwidths). History, ids and the logs (0005) come from these.
- Each provider is checked through the company's connection for it, so credentials, platform
  limits and logging work exactly as in bulk runs (`credentials_of`, the Recorder). Products map
  from Rapid's ids through `CatalogueProduct` to the company's `ProviderProduct`.
- The request waits for the answers: one Hatchet task per connection, ahead of bulk work, and
  the view awaits the results (Daphne, async view, woken over `LISTEN`/`NOTIFY`) until the
  timeout. Whatever didn't finish is listed in `exceptions`, as Rapid did.
- Feasible means `available` (and Vodacom's coverage-only media the definition already counts
  as feasible), matching Rapid.
- **Pricing:** a definition applies when its access medium (Vodacom) or catalogue product (MTN)
  was found feasible and its `max_bandwidth` is one of the upper limits offered there.
- **Only Vodacom and MTN are priced**, as in Rapid (decided: Ruan, 2026-11-17). Link Africa and
  Herotel are still checked by `single-site-feasibility`, but a quote lists no prices for them,
  even when they're feasible and the price book has definitions for them.

### Isolation
Every new endpoint gets the five checks; and also: an API client's token works only in its own
company and only within its scopes; a company without a grant sees no price book; one company's
site checks and their ids never show to another; the price book admin is staff-only.

## Scenarios

### AT-0006-01 — Staff import Rapid's price book with its ids
- Given a Rapid price book dump (invented data)
- When staff run `import_rapid_pricebook`
- Then every connect product, definition, catalogue product and access medium exists with its
  Rapid id and values, and running it again changes nothing

### AT-0006-02 — Staff import price definitions from Rapid's CSV
- Given Rapid's CSV template filled in, with "on Request only" and "Unrestricted" values
- When staff import it in Django admin
- Then the definitions exist, POA as -1, linked to the connect products named in the file

### AT-0006-03 — Staff download the price book as CSV and PDF
- When staff export the price book
- Then the CSV has Rapid's columns, Vodacom first by access medium, POA where the price is -1
- And the PDF lists every definition by medium and provider

### AT-0006-04 — An admin creates an API client and sees its secret once
- Given I am an Admin
- When I create an API client with `feasibilities.run` and `feasibilities.quote`
- Then I see its client id and secret, and afterwards only its id

### AT-0006-05 — A client gets a token and works in its own company without X-Realm
- Given an API client of Acme
- When it gets a token and calls `GET /api/product/` with no `X-Realm`
- Then it gets Acme's view of the products

### AT-0006-06 — A client can't do more than its scopes
- Given an API client with `feasibilities.run` only
- When it asks for a quote
- Then it gets 403

### AT-0006-07 — A revoked client's token stops working
- When an Admin revokes a client
- Then its existing token gets 401 on the next call

### AT-0006-08 — Connect products list matches Rapid
- Given Acme is granted the price book
- When its client lists connect products
- Then the response matches Rapid's recorded response field for field, paginated by 20

### AT-0006-09 — A single-site check matches Rapid's response
- Given Acme's Vodacom and MTN connections, and providers answering from recordings
- When its client checks a site for chosen products
- Then the response matches Rapid's recorded response field for field

### AT-0006-10 — A quote matches Rapid's response
- Given the same site and answers
- When its client asks for a quote for chosen connect products
- Then prices, grouping, ids, `provider_id` and the notice match Rapid's recorded response

### AT-0006-11 — Only definitions at an offered bandwidth are priced
- Given Vodacom offers 100-1000 and 1000 Mbps on Fibre, and 0-50 on LTE
- When a quote is asked for
- Then definitions at 1000 (Fibre) and 50 (LTE) are listed, and one at 100 on Fibre isn't

### AT-0006-12 — A provider that fails or times out is listed, the rest still answer
- Given MTN times out and Vodacom answers
- When a quote is asked for with a 5 second timeout
- Then the answer comes back within about 5 seconds, priced from Vodacom, with MTN in
  `exceptions`

### AT-0006-13 — A provider the company isn't connected to is listed, not checked
- Given Acme has no Herotel connection
- When it checks Herotel products
- Then Herotel is in `exceptions` as not connected, and no Herotel call is made

### AT-0006-14 — Bad requests get Rapid's errors
- When a client sends an unknown connect product, no latitude, or a timeout of 60
- Then it gets 400 with Rapid's error body for each

### AT-0006-15 — A company without a grant sees no price book
- Given staff limited the price book to granted companies, and Globex isn't granted it
- When its client lists connect products or asks for a quote
- Then it gets 403, and nothing of the price book is shown

### AT-0006-16 — One-site checks use the company's own credentials and are logged
- Given Acme uses Telejects' Vodacom account and its own MTN account
- When it checks a site
- Then each call uses the right credentials and appears in Acme's Logs, secrets redacted

### AT-0006-17 — Another company's checks and clients stay out of sight
- Given Acme and Globex each have checks and API clients
- When Globex's admin or client looks
- Then none of Acme's checks, results or clients are seen, by id or in a list

### AT-0006-18 — Link Africa and Herotel aren't priced
- Given Link Africa is feasible at a site and the price book has Link Africa definitions
- When a quote is asked for
- Then no Link Africa prices are listed, as in Rapid

## Decisions
- Only Vodacom and MTN are priced, as in Rapid (Ruan, 2026-11-17).
- `timeout` defaults to 50 seconds, Rapid's request default.
- The PDF's provider logos are copied from Rapid into the repo.
- One spec: API clients are built here, as the first thing these endpoints need.
- The price book is offered to every company by default, matching 0004 as it now stands.

## Implementation notes

**Built.** Three new apps and a page:
- `apps/pricebook`: the price book models (`models.py`, Rapid's ids and field names), Rapid's
  response shapes and the single-site and quote logic (`services.py`), the endpoints at Rapid's
  paths (`views.py`, `urls.py`), Rapid's CSV import, template, CSV export, the PDF and the dump
  import (`books.py`), Django admin with import and export links on the price definitions list
  (`admin.py`), `manage.py import_rapid_pricebook`, a migration that makes the "Telejects" book,
  and the expected Rapid responses for the contract tests (`rapid_responses/`).
- `apps/api_clients`: `ApiClient` (one per django-oauth-toolkit Application, secret hashed),
  `ApiClientAuthentication` (the token's request user is an `ApiClientUser` whose
  `ClientMembership` answers `has_perm` from the client's codes and its maker's current ones),
  create, list, revoke and `permissions/` at `/api/api-clients/`, and the token endpoint
  `/api/oauth/token/` (DOT's `TokenView` inside a DRF view, throttled 30 a minute).
- `apps/site_checks`: `SiteCheck`, `SiteCheckCall` (one per provider) and `SiteCheckResult`;
  `start_check`, `wait_for` and `perform_call` (`services.py`); the `site-check-call` Hatchet
  task at priority 3 under the same per-credentials limits as bulk checks (`tasks.py`).
- `InRealm` (`realms/permissions.py`) takes the company from an API client's token; an X-Realm
  naming another company gets the non-member refusal.
- Portal: an **API clients** page at `/developers` (sidebar, `api_clients.manage`): list,
  create (the secret shown once, with copy buttons), revoke, and how a client connects.
- Permission codes: `feasibilities.quote` (Admin, Project manager) and `api_clients.manage`
  (Admin). Dependencies: `django-oauth-toolkit`, `reportlab`.

**Later: Developers and the API docs** (Ruan, 2026-11-20).
- The sidebar section is **Developers** (`/developers`), with tabs: **Server credentials**
  (`/developers/credentials`, the API clients page as it was) and **API documentation**, a link
  that opens `/api/docs/` in a new tab.
- `/api/docs/` is Redoc over an OpenAPI 3.1 schema (`/api/docs/schema/`) generated by
  `drf-spectacular`. Both are public (allowlisted in `test_isolation.py`) and describe only what
  an API client can call: the token endpoint and the views listing `ApiClientAuthentication`
  (`api_clients/openapi.py`'s preprocessing hook). The web app's own endpoints stay out.
- Rapid's responses are built by hand, so `pricebook/openapi.py` describes them with
  documentation-only serializers, and its examples are the contract responses in
  `rapid_responses/`. `pricebook/test_api_docs.py` validates those responses, a real token and a
  real product page against the published schema (no undocumented fields), checks the docs list
  exactly the client endpoints, and fails on any schema warning.
- Redoc loads from jsDelivr, pinned to 2.5.0 (`REDOC_DIST`): its latest no longer ships the
  standalone script. The page is kept light, as Redoc has no dark theme.

**Deviations from the design, and why.**
- **One-site checks are their own app** (`site_checks`), not part of `feasibilities`: the map
  screen (next spec) will use them too, and they share no tables with bulk runs.
- **Waiting is a short database poll** (every 0.2 s, until every call answers or the timeout),
  in a plain sync view, not an async view woken by `LISTEN`/`NOTIFY`. It holds one Daphne
  thread for at most `timeout` seconds and only reads one company's rows. Worth revisiting if
  many clients call at once.
- **Client tokens work only where a view opts in** (`ApiClientAuthentication` on the four
  Rapid endpoints). Everything else stays JWT only, so a client token can never reach `me`,
  password changes or the company's own API. That is also why a client can be given only
  `feasibilities.run` and `feasibilities.quote` for now (`CLIENT_PERMISSIONS`).
- **The page is `/developers`, not `/api-clients`**: Vite's dev proxy sends every path starting
  with `/api` to Django.
- **Vodacom's coverage-only media** (Rapid's `TEMP_VODACOM_HACK_FIX_ITEMS`) count as feasible
  for these endpoints only (`SiteCheckResultQuerySet.feasible`); the Vodacom definition still
  calls them coverage only, as bulk runs show.
- **Rapid's CSV import** reads "MRC on Request only" and "NRC on Request only" (Rapid's words)
  as well as "POA" for price on request.
- **The PDF** lists every definition, including those without a sublayer or product, which
  Rapid's left out. Skybird's own logo isn't copied; the sublayer logos are.
- **When no products are named**, `single-site-feasibility` asks about the catalogue products of
  the providers the company is connected to, not every product (Rapid's default), so an
  unconnected provider isn't reported on every call.
- **Exceptions** name the error kind (`Timeout`, `ProviderDown`, `Auth`, `NotConnected`,
  `NotOffered`) instead of a Python class name; the shape is Rapid's.
- **Access media** first seen in a Vodacom answer are created, as Rapid did, so quotes can match
  them.
- A deleted company's API clients take their OAuth applications with them.

**Checked.** `make test` and `make check` pass. Against the running local API: a client created
on the page got a token, listed products and connect products, ran a single-site check, was
refused on `/api/auth/me/`, and after revoking on the page could no longer get a token. A
one-site check ran through a real local Hatchet worker with the Demo provider (about 3 s,
result written, request logged). The page was checked in dark and light, and at phone width.

**Not checked.** No live call to Vodacom, MTN, Link Africa or Herotel; those are covered by the
recorded fakes only. The contract responses are derived from Rapid's code, not captured from
Rapid, so one capture from Rapid with the same price book would be worth comparing before
clients switch. `import_rapid_pricebook` hasn't been run on a real Rapid dump; Link Africa's and
Herotel's catalogue product codes will need mapping in Django admin afterwards.
