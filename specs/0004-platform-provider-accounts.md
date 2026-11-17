# 0004 — Telejects' provider accounts, shared with chosen companies

- **Status:** Done
- **Depends on:** 0003
- **Django apps:** `integrations` (platform accounts, grants, which credentials a connection
  uses); `feasibilities` (limits and records per credential)
- **Touches:** backend / frontend / jobs

## Why
In Rapid, every company checks feasibility with Skybird's own MTN, Vodacom, Herotel and Link
Africa accounts. Most customers don't have provider API access of their own, and shouldn't need
it to get started. 0003 made each company bring its own account. Telejects needs both: its own
accounts as the default for the companies staff choose, and a company's own account instead
when it has one.

## Scope
- In:
  - **Platform accounts:** Telejects' own credentials for a connector, kept by platform staff,
    encrypted like a company's, never shown to any company.
  - **Grants:** staff choose which companies may use which platform account.
  - A granted company is connected to that provider straight away, through Telejects' account,
    and can run feasibilities with it.
  - An Admin can switch a provider to the company's own account (filling in the fields as in
    0003), and back to Telejects' account while the grant lasts.
  - Withdrawing a grant turns off the connections using it.
  - Provider limits are shared by everyone using one platform account.
  - Every provider call records whose credentials it used, so usage per company can be counted
    later.
- Out (later specs):
  - Billing or quotas for using Telejects' accounts.
  - Usage reports per company (the records are kept from this spec on).
  - Companies asking for access from the portal: staff grant it.
  - Notifying staff by email when a platform account fails (it shows in Django admin).

## Design notes

### Rule change
CLAUDE.md says provider credentials, requests and results belong to a company. After this
spec: **requests and results always belong to a company; credentials belong to the company, or
to the platform when staff have granted the company a platform account.** A company never sees
a platform account's settings or secrets, and nothing else about it crosses between companies.

### Data
- **`PlatformAccount`** (platform data, not a `TenantModel`; allowlisted with that reason):
  connector key, name (e.g. "Telejects MTN"), settings, enabled, health (as a connection's),
  created and updated. Its secrets are not in the database: they come from `.env` through
  settings (decision 7).
  Several per connector are allowed (e.g. a second MTN account for a large customer).
- **`PlatformGrant`** (`TenantModel`): a company may use one platform account. Unique per
  company and account. Created and withdrawn by staff only, in Django admin or with
  `manage.py grant_platform_account <company id> <account id>` (and `--withdraw`).
- **`Connection`** gains `credentials`: `own` or `platform`, and `platform_account` (set when
  `platform`). A `platform` connection has no settings or secrets of its own. It may only
  point at an account its company has a grant for (checked in services, and by a test).

### How credentials are chosen
`integrations.services.connector_for(connection)` is the one place that decides: a `platform`
connection gets the platform account's settings and secrets, an `own` one its own. Nothing else
reads secrets. A `platform` connection whose grant is gone, or whose account is off, fails with
"Telejects' account for this provider isn't available to you any more."

### Granting, switching, withdrawing
- **Granting** creates the company's connection for that provider ("MTN Business (Telejects
  account)", `platform`), then tests it and syncs its products, as connecting does in 0003. If
  the company already has its own connection to that provider, the grant only makes the switch
  available and changes nothing.
- **Switching to our own** (an Admin, `integrations.manage`): fill in the connector's fields; the
  connection becomes `own`, is tested and re-synced. Products the new account doesn't offer are
  retired, as in any sync.
- **Switching back** (while granted): the connection becomes `platform`, its own secrets are
  deleted, and it is tested and re-synced.
- **Withdrawing** turns off every connection of that company using the account. Its runs and
  results stay. Running checks on it fail with the "not available" message.

### Limits and health
- Hatchet's concurrency and rate-limit keys become the **credential's**: `platform-<id>` for a
  platform account, `connection-<id>` for a company's own. Ten companies on Telejects' MTN
  account share MTN's limit, as the provider sees one account.
- A platform account's credential check runs once on the schedule (not once per company), and
  its health shows on every connection using it.
- An `auth` refusal of a platform account marks the account failing (every company using it
  sees "Telejects' account for this provider is failing; we're on it") and fails only that run's
  remaining checks with it. Staff see it in Django admin.
- Catalogue syncs stay per connection, so each company's products and history stay its own,
  with the platform account's credentials used for the call.

### Records
`ProviderCheck` and `SyncRun` gain `credentials` (`own` or `platform`) and `platform_account`
(when platform), so usage per company per account can be counted later. Recorded calls redact
the platform account's secrets as they do a company's.

### API and portal
- A connection shows `credentials` ("Telejects account" or "Your account"). For `platform` it
  shows no settings, no `secrets_set` and no form; a link "Use our own account instead" opens the
  connector's form. For `own` with a grant, a link "Use Telejects' account instead".
- `PATCH /api/integrations/connections/<id>/` takes `credentials` (`own` with `fields`, or
  `platform`). Switching to `platform` without a grant is refused like an unknown account.
- The Available providers list shows "Included: Telejects account" on connectors the company is
  granted, so it doesn't connect a second account by mistake.
- No new permission codes: switching is `integrations.manage`; seeing is `integrations.view`.

## Scenarios

### AT-0004-01 — A granted company is connected with Telejects' account
- Given staff grant Northwind Fibre Telejects' MTN account
- Then Northwind's Integrations shows MTN Business as "Connected · Telejects account", with
  products, and it can run feasibilities with it

### AT-0004-02 — A company never sees Telejects' credentials
- Given Northwind uses Telejects' MTN account
- When anyone in Northwind opens or lists its connections, sync history, runs or exports
- Then no setting or secret of the platform account appears, and there is no form to see them

### AT-0004-03 — A company without a grant can't use Telejects' account
- Given Blue Mast has no grant
- Then it sees no Telejects account, and switching a connection to `platform` is refused

### AT-0004-04 — I switch to our own account
- Given Northwind uses Telejects' MTN account
- When an Admin chooses "Use our own account instead" and fills in the fields
- Then the connection uses Northwind's credentials, is tested and re-synced, and later runs call
  MTN with Northwind's key

### AT-0004-05 — I switch back to Telejects' account
- Given Northwind's MTN connection uses its own account and the grant still stands
- When an Admin chooses "Use Telejects' account instead"
- Then its own secrets are deleted, it uses Telejects' account again, and is re-tested

### AT-0004-06 — Withdrawing a grant turns the connection off
- Given Northwind uses Telejects' MTN account
- When staff withdraw the grant
- Then the connection is off, new runs can't pick its products, and past runs and results stay

### AT-0004-07 — A company that already has its own account keeps it
- Given Northwind connected its own MTN account
- When staff grant it Telejects' MTN account
- Then its connection still uses its own account, and "Use Telejects' account instead" appears

### AT-0004-08 — Companies on one account share the provider's limits
- Given Northwind and Blue Mast both use Telejects' MTN account
- Then their checks share one concurrency and rate limit, while a company's own account has its
  own

### AT-0004-09 — A failing Telejects account shows everywhere it's used
- Given Telejects' MTN account starts being refused
- Then every company using it sees it failing, staff see it in Django admin, and companies on
  their own MTN accounts are unaffected

### AT-0004-10 — Every call says whose credentials it used
- When a run checks sites with Telejects' account and with a company's own
- Then each provider call is recorded with `platform` (and which account) or `own`

### AT-0004-11 — Only Admins switch, only staff grant
- A Project manager can't switch credentials, and nobody can grant or withdraw from the portal

### AT-0004-12 — Companies stay apart on a shared account
- Given two companies run feasibilities on Telejects' MTN account at the same time
- Then each sees only its own runs, results, products and sync history, and a grant to one never
  shows in the other

## Decisions
Decided with Ruan:
1. Telejects' accounts are the default only for companies staff grant them to (not every
   company automatically).
2. Written as a new spec; 0003 stays the record of what it built.

Open until Ruan approves the spec:
3. **Product syncs per connection** (drafted) or once per platform account and shared by every
   company on it. Per connection keeps each company's catalogue its own, at the cost of N calls
   to the provider per sync.
4. **Switching to own deletes nothing old**, but switching back to Telejects' deletes the
   company's own secrets (drafted), rather than keeping them for another switch.
5. **What companies see when Telejects' account fails**: drafted as "failing; we're on it", with
   no detail from the provider.
6. **Existing data:** none to migrate (0003 has only own connections), so all existing
   connections become `own`.
7. **Platform secrets in `.env`** (decided by Ruan after the build; see 8 for settings): Telejects' own provider
   keys are environment values (`PLATFORM_MTN_API_KEY`, `PLATFORM_VODACOM_AUTH_KEY`,
   `PLATFORM_HEROTEL_API_KEY`, `PLATFORM_LINK_AFRICA_KEY`), read into
   `INTEGRATIONS_PLATFORM_SECRETS`; a platform account names its entry with `secrets_key`.
   Companies' own credentials stay in the database, encrypted with Fernet.
8. **Every provider, active from the start** (decided by Ruan, 2026-11-17, replacing decision 1
   for accounts configured in `.env`):
   - Telejects' accounts are configured entirely in `.env`: secrets and settings
     (`INTEGRATIONS_PLATFORM_ACCOUNTS`, from `PLATFORM_*`). A row per provider whose secrets
     are all set is made by `ensure_platform_accounts`, run by `load_connectors` (`make
     migrate`) and the hourly `integrations-due` job.
   - Such an account is `available_to_all`: every company is connected to it from the start
     (on creation, through a signal on `Realm`, and existing ones by `ensure_everywhere`).
     Staff can turn `available_to_all` off; the account is then for granted companies only, as
     decision 1 had it.
   - The Integrations page shows a card per provider, saying whose account it uses, with the
     override: "Use your own account" (the connector's form) and "Use Telejects' account" back.
   - A provider whose `.env` key is removed becomes unavailable to companies on Telejects'
     account; those with their own account carry on.
   - Demo, where it's enabled, is offered the same way (it needs no credentials).
   - Herotel and Link Africa were added from Rapid at the same time (connector definitions only).

## Implementation notes

Built as approved, with decisions 3–6 as drafted. Decisions 7 and 8 came after, from Ruan:
`PlatformAccount` keeps `env_key` and `available_to_all` and reads its secrets and settings
from `.env` (migrations `integrations/0003`, `0004`); `services.ensure_platform_accounts`,
`ensure_default_connections` and `ensure_everywhere`; the `Realm` signal in
`integrations/apps.py`; `features/integrations/components/provider-card.tsx` and
`own-account-dialog.tsx`; tests in `apps/integrations/test_defaults.py` (including Herotel's and
Link Africa's mappings). Checked live: Vodacom, Herotel and Link Africa accept Telejects' keys
and answer through the worker; MTN's host answers 503 to every request.

- **Models (`apps/integrations/models.py`):**
  - An abstract `Credentials` base (connector key, settings, encrypted secrets, enabled,
    health) shared by `Connection` and the new `PlatformAccount` (platform data, allowlisted).
  - `PlatformGrant` is a `TenantModel`.
  - `Connection` gains `credentials` and `platform_account`, with a database check that they
    agree.
  - `SyncRun` and `ProviderCheck` record `credentials` and `platform_account`.
  - Migrations: `integrations/0002`, `feasibilities/0004` and `0005`.
- **Services (`apps/integrations/services.py`):**
  - `credentials_of` is the one place that picks the credentials. It needs a live grant and an
    enabled account, or the call fails with "isn't available to you any more".
  - `grant_platform_account` and `withdraw_platform_account`.
  - `update_connection(credentials=...)` switches. Switching back deletes the company's own
    settings and secrets.
  - Health goes to the platform account when a platform connection is checked, and every
    company using it is told.
  - Credential checks run once per platform account on the schedule
    (`integrations-test-platform-account`); product syncs stay per connection.
- **Limits:** `Connection.limit_key` (`platform-<id>` or `connection-<id>`) is now the Hatchet
  concurrency and rate-limit key for `feasibility-check`.
- **API:**
  - A platform connection shows no settings or secrets, and its health in our words.
  - Connections show `credentials` and `can_use_platform`; connectors show `included`.
  - `PATCH` takes `credentials`.
- **Staff:**
  - Django admin for platform accounts: settings and the `secrets_key` are edited there; the
    secrets are not. It shows only whether `.env` has each one, and an action checks the
    credentials now. (Migration `integrations/0003` dropped the encrypted column.)
  - Django admin for grants: saving grants, deleting withdraws.
  - `manage.py grant_platform_account <company> <account> [--withdraw]`.
- **Portal:** connections say "Telejects account". The Account section offers "Use our own
  account instead" (the connector's form, keeping the connection's name) and "Use Telejects'
  account instead". Providers the company is granted show "Included: Telejects account" instead
  of Connect.
- **Tests:**
  - `apps/integrations/test_platform.py`: scenarios 01–12, plus the database check and the
    admin keeping secrets write-only.
  - The isolation guards list `PlatformAccount` and `_publish_platform`, with reasons.
- **Deviation:** the Hatchet task that checks a platform account carries only the account's id,
  not a `realm_id`. It works on platform data and changes no company's rows except through the
  events it publishes.
- **Checked in the running app** (a throwaway company and platform account, deleted
  afterwards):
  - granting (the connection named "Demo (Telejects account)", "Included" on the card, and no
    settings or secrets shown);
  - switching to own and back, with the stored credentials cleared;
  - the Integrations pages in light and dark mode and at phone width.
- **Not checked live:**
  - A feasibility run on a platform account through Hatchet. Ruan's running worker predates
    this spec: it fails to insert sync records now that the `credentials` column exists, and its
    `feasibility-check` expects the old input. I ran the connect operation from a shell with the
    new code instead. The tests cover runs on platform accounts inline. Restart the worker
    (`make worker`).
