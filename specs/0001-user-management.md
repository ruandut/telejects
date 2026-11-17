# 0001 — Companies and user management

- **Status:** Done
- **Depends on:** the scaffold (sign-in, `accounts.User`, Hatchet)
- **Django apps:** new `realms` (companies, memberships, the tenancy gate); new `users` (managing
  people, invitations)
- **Touches:** frontend / backend / jobs

## Why
Telejects serves many companies, each running its own telecoms projects. Before any project data
exists, every company needs a space of its own that no other company can see into, and its
admins need to manage their own people from the portal: add them, decide who is an admin and
remove them when they leave.

## Scope
- In:
  - **Companies** as the unit of tenancy. Every later domain row belongs to exactly one company,
    and every API request works inside one company the user is an active member of.
  - The tenancy guard rails, built the same way as eden-tracker's realms and in place before the
    first domain model: `TenantModel`, `InRealm`, realm-scoped viewsets and serializers, and the
    two guard tests (every `/api/` route gated or allowlisted, every model a `TenantModel` or
    allowlisted).
  - A **User management** section listing the company's people, their roles and status.
  - Add users with a specific role, change a user's role, edit and remove users.
  - **Roles** from a fixed list (Admin, Project manager, Field technician, Viewer), each a set of
    permissions. Access is checked by permission, never by role name, and roles are stored per
    company so a later spec can let companies define their own.
  - A company always has at least one Admin.
  - A new user gets an email with a link, and confirms their account by setting a password.
  - Someone in more than one company switches between them from the sidebar.
- Out (later specs):
  - Creating a company from the portal, or signing up. Platform staff create a company and its
    first admin with a management command (or Django admin) for now.
  - Forgotten-password reset, changing my own password and editing my own profile.
  - Companies creating, editing or deleting their own roles (custom roles). This spec lays the
    data out for it; a later spec adds the role editor.
  - A customer role that sees only their own projects (needs projects first).
  - SSO and two-factor sign-in.
  - Billing, plans and limits per company.

## Design notes

**What a realm is.** A realm is a company using the platform: the tenant. A company runs many
projects, and every project (and everything under it: sites, feasibilities, tasks) belongs to
exactly one realm. Users are members of realms, not of projects; access within a company's
projects is a later spec's concern.

**Naming.** People see "company"; the code keeps eden-tracker's names (`apps/realms`, `Realm`,
`RealmMembership`, `X-Realm`), so the two projects read the same and the tenancy code can be
ported as is. (Open: see Decisions 1.)

**Tenancy is the most important part of this spec.** A leak across companies is the worst bug
Telejects can have. `apps/realms` is a dedicated platform app whose only job is tenancy, and it
is built first, before user management and before any domain model. Every endpoint, in this spec
and every later one, ships with isolation tests in the same change, in
`apps/realms/test_isolation.py`, covering all five of these:
1. another company's rows stay out of lists, counts and aggregates;
2. detail routes and custom actions on another company's rows return 404, for every method, and
   the row is unchanged afterwards;
3. a foreign key in a request body can't point into another company;
4. a non-member sending that company's `X-Realm` gets 403;
5. permission limits hold (someone without a permission can't do what it allows).

Two guard tests make skipping the pattern fail the build: every `/api/` route must be
company-gated or on an allowlist with a written reason, and every model in `apps/` must be a
`TenantModel` or allowlisted with a reason. An allowlist is never extended just to make a test
pass. Background tasks take a `realm_id` and filter by it. Any future websocket admits only an
active member of the company it names, and never carries data. An endpoint is not done until
its isolation tests pass.

**Realm filtering lives on the queryset managers.** Every tenant model's manager is built on
`TenantQuerySet` (`apps/realms/querysets.py`), and each app's own queryset extends it, so
company scoping is the first link of every query: `Project.objects.in_realm(realm).open()`.
- `in_realm(realm)` scopes to one company; `in_realm_id(realm_id)` does the same for Hatchet
  tasks, which carry an id rather than a request.
- **Unscoped queries fail.** A `TenantQuerySet` that is evaluated (iterated, counted, fetched,
  aggregated, updated or deleted) without `in_realm` raises `UnscopedQuery`, rather than
  quietly returning every company's rows. The rare platform-wide use (Django admin, a migration,
  a staff report) calls `.across_realms()` explicitly, and each such call site is on an
  allowlist in `test_isolation.py` with a reason.
- Related-object lookups are scoped too: `get_queryset()` in `RealmScopedViewSet` starts from
  `in_realm(request.realm)`; `RealmScopedSerializer` limits every related field's queryset to
  `request.realm`, so a foreign key can't point into another company.
- Domain query methods (`open()`, `overdue()`, ...) assume a scoped queryset and never take a
  realm themselves: the realm is set once, at the start of the chain.
- Django uses the plain base manager for related access (`task.project`), which is safe because
  it starts from a row the request could already see.

**`realms` (platform app)** owns `Realm`, `RealmMembership` (user, realm, role, status, name),
`TenantModel`, `TenantQuerySet` (`in_realm`, `by_id`), the `InRealm` permission (resolves the
company from `X-Realm`, refuses anyone without an active membership, sets `request.realm` and
`request.membership`), `HasRealmPermission`, `Role` and the permission registry, `RealmScopedViewSet` / `RealmScopedSerializer`, and
`apps/realms/test_isolation.py` with the two guard tests. `InRealm` joins `IsAuthenticated` as a
default permission class. The existing `apps/core/test_access.py` folds into the isolation test's
allowlist. `/api/auth/me/` grows `realm` (the company this request works in, or null) and
`realms` (the companies I belong to), never mentioning any other company.

**`users` (platform app)** owns `Invitation`, the endpoints, services and queries for managing
people, the invitation email task and the public confirmation route. It may import `core`,
`accounts`, `realms` and `jobs`. Only `users/services.py` changes a membership's name, role or
status.

**A "user" here is a membership.** One account per email address can belong to several
companies. What an admin manages is stored per company, on the membership, so an admin in one
company can never change what another company sees:

| Field | Lives on | Who changes it |
|---|---|---|
| Email | account | set when added; fixed afterwards |
| Name | membership | users with `users.manage` |
| Role | membership (a company's `Role`) | users with `users.manage` |
| Status (invited / active / removed) | membership | the system |

**Roles and permissions.** Built so custom roles can come later without migrating data:
- **Permissions are codes defined in code**, in one registry (`apps/realms/access_control.py`):
  `users.view` (see the user list), `users.manage` (add, edit, remove, invite and change roles).
  Each later spec adds the codes it needs (`projects.edit`, `feasibilities.run`, ...) and says
  which built-in roles get them. Nothing checks a role's name.
- **A `Role` is a company's row** (`TenantModel`): `key`, `name`, `is_system`, and a `permissions`
  list used only by custom roles. Every new company gets the four built-in roles, with
  `is_system=True`. A built-in role's permissions are read from the registry in code, not the
  row, so adding a permission to "Project manager" in a later spec reaches every company
  without a data migration.
- **The built-in roles** in this spec:

  | Role | `users.view` | `users.manage` | Meant for |
  |---|---|---|---|
  | Admin | yes | yes | running the company's account; always has every permission |
  | Project manager | yes | no | planning and running projects |
  | Field technician | no | no | doing the work on site |
  | Viewer | no | no | read-only access |

- **A membership points at one `Role` of the same company**: a foreign key, checked to be in the
  membership's company in the service and by a database constraint on `(realm, role)`.
- `HasRealmPermission("users.manage")` replaces "is admin" checks in DRF;
  `request.membership.has_perm(code)` in code. `/api/auth/me/` returns my role and my
  permissions in this company, and the frontend shows or hides things by permission.
- Later, custom roles are rows with `is_system=False` and their own `permissions`; only the role
  editor is new.

**Adding a user** creates the membership as *invited* and sends the email. The response is the
same whether or not the address already has an account in another company, so adding can't be
used to find out who uses Telejects. An invited user can't work in the company.

**The link** carries a single-use token, valid for 7 days. Only a hash is stored; the token is
made by the email task when it sends, so it never sits in the queue or the database in the
clear. Opening it shows the company name and the email address. A new person sets a password
(Django's validators, 12 characters minimum) and is signed in; someone who already has an
account just confirms, then signs in with their existing password. Admins can resend (which
replaces the old link) or cancel a pending invitation.

**Email** is sent by a Hatchet task, enqueued on commit. Without `EMAIL_URL` in `.env` it is
printed to the worker's log, link included.

**The last Admin.** Removing the only Admin needs another active user chosen to take over, in the
same transaction; the same applies when the only Admin removes themself. The only Admin's role
can't be changed, and the only active user can't be removed.

**Removing a user** ends their access on their next request. The membership is kept as *removed*
rather than deleted, so their past work on projects stays attributable. A removed user doesn't
appear in the list, and their email can be added again later.

**Switching company.** The tab's company is held in a Zustand store and sent as `X-Realm`;
switching goes through one `enterRealm()` that drops the old company's cached data. With no
`X-Realm`, the server picks the first company the user is active in. A user with no active
company sees a "You're not part of any company yet" screen rather than a broken dashboard.

**Designed for later: board-based (per-project) access.** Not built in this spec, but 0001 must
not make it hard. A company will be able to give someone access to one project only, like a board
in monday.com. The first case is a guest outside the company: Northwind Fibre runs a project to
install internet at a restaurant chain's sites, and someone at the chain follows its progress.
That person sees that project and nothing else in the company, and nothing in any other
company. Internal users may later get per-project roles the same way. What 0001 does so this
fits:
- A guest is still a `RealmMembership` of the company, so `InRealm`, the realm-scoped managers
  and the isolation tests keep working unchanged. Being in the realm only gets you to the
  door; it is not the same as seeing all of its projects.
- What a membership can see is decided by its permissions. Seeing every project in the company
  will be a permission (`projects.view_all`) that the built-in staff roles get and a guest role
  never does. The projects spec adds project grants (membership, project, project role) and a
  `visible_to(membership)` queryset method that every project-owned query chains after
  `in_realm`.
- `has_perm(code)` takes an optional project from the start, `has_perm(code, project=None)`,
  so project-level checks slot in without changing every call site. In 0001 the project is
  always `None`.
- The isolation tests gain a sixth check when projects arrive: a guest sees only the projects
  granted to them, through lists, details, aggregates, search and files.
- Guests never see User management, the company's other users, or the company's other projects'
  names.

**Seeding.** `make seed` creates the local sign-in as admin of a first company. A new
`create_company` command (name, admin email) is how platform staff add a company until a spec
covers it; it sends the first admin an invitation.

**Endpoints** (all gated by `InRealm`; reads need `users.view`, writes `users.manage`):

| Method | Path | Does |
|---|---|---|
| GET | `/api/users/` | list active and invited users |
| POST | `/api/users/` | add a user and send the invitation |
| GET / PATCH | `/api/users/{id}/` | read; change name, role |
| GET | `/api/roles/` | the company's roles, with their permissions (for the role picker) |
| DELETE | `/api/users/{id}/` | remove; body `new_admin` when they are the last admin |
| POST | `/api/users/{id}/resend/` | send a fresh link to an invited user |
| GET / POST | `/api/users/invitations/{token}/` | public: describe the link / confirm it |

The public route joins the allowlist in `test_isolation.py`. It reveals only the company name
and the invited address, and only to someone holding the token.

**The User management screen** (`/users`, "User management" in the sidebar, shown to anyone
with `users.view`):
- A table of active and invited users: name, email, role, status, and when they joined. Filter
  by role and status, search by name or email. On a phone it becomes a list of cards.
- **Add user** (with `users.manage`): name, email and a role picked from the company's roles,
  each with a one-line description of what it can do. Sends the invitation.
- Each row's menu: change role, edit name, resend or cancel an invitation, remove. Removing the
  last Admin asks who takes over.
- Without `users.manage` the table is read-only and the actions don't show.

**Frontend:** `src/stores/realm.ts`, `src/features/realms/` (gate, switcher, a `usePermission`
hook), `src/features/users/`, `src/routes/_app/users/`, and a public
`src/routes/accept-invite.tsx` styled like the sign-in page.

## Scenarios

Invented companies: "Northwind Fibre" and "Blue Mast Telecom".

### Managing users

#### AT-0001-01 — An admin sees the company's users
- Given I am an Admin of "Northwind Fibre"
- When I open User management
- Then I see each user's name, email, role and status

#### AT-0001-02 — An admin adds a user
- Given I am an admin
- When I add "Thandi Nkosi" with email "thandi@example.com" as a Field technician
- Then she appears in the list as a Field technician, "Invited"
- And an invitation email is sent to "thandi@example.com"

#### AT-0001-03 — The same email can't be added twice
- Given "thandi@example.com" is already a user in my company
- When I add "thandi@example.com" again
- Then I see "They're already a user here"
- And no email is sent

#### AT-0001-04 — An admin edits a user
- Given "Thandi Nkosi" is a Field technician
- When I change her name to "Thandi Dlamini" and her role to Project manager
- Then the list shows "Thandi Dlamini" as a Project manager

#### AT-0001-05 — An admin removes a user
- Given "Thandi Nkosi" is an active Field technician
- When I remove her and confirm
- Then she is no longer in the list
- And she can no longer see anything in the company

#### AT-0001-06 — Without the permission, users can't be managed
- Given I am a Project manager
- When I open User management
- Then I see the users but no way to add, edit or remove them
- And adding, editing, removing or changing a role through the API is refused

#### AT-0001-07 — Some roles don't see users at all
- Given I am a Field technician or a Viewer
- Then User management isn't in my sidebar
- And listing users through the API is refused

#### AT-0001-08 — An admin cancels an invitation
- Given "Sam Pillay" is invited
- When I cancel his invitation
- Then he is no longer in the list
- And the link in his email no longer works

### Always an admin

#### AT-0001-09 — Removing the only Admin hands the role over
- Given I am the only Admin and "Thandi Nkosi" is an active member
- When I remove myself
- Then I must choose who becomes Admin
- When I choose "Thandi Nkosi" and confirm
- Then she is an Admin and I no longer have access to the company

#### AT-0001-10 — The only Admin can't be removed without a successor
- Given I am the only Admin
- When I try to remove myself without choosing anyone
- Then I see "Choose who takes over as Admin"
- And nothing changes

#### AT-0001-11 — The successor must be an active user of this company
- Given I am the only Admin and "Sam Pillay" is invited but hasn't confirmed
- When I remove myself
- Then "Sam Pillay" isn't offered as a successor

#### AT-0001-12 — The only Admin's role can't be changed
- Given I am the only Admin
- When I change my role to Project manager
- Then I see "A company needs at least one Admin"

#### AT-0001-13 — With another Admin, no successor is needed
- Given "Thandi Nkosi" and I are both Admins
- When I remove her
- Then I am not asked to choose a successor

### Roles

#### AT-0001-14 — Every company starts with the built-in roles
- When a company is created
- Then it has Admin, Project manager, Field technician and Viewer
- And its first user is an Admin

#### AT-0001-15 — I pick a role when adding someone
- Given I am adding a user
- Then I choose from my company's roles, each with what it can do
- And I can't add a user without a role

#### AT-0001-16 — A changed role takes effect at once
- Given "Thandi Nkosi" is a Project manager and can see User management
- When I change her role to Field technician
- Then on her next request she can no longer list users

#### AT-0001-17 — Access follows permissions, not role names
- Given a built-in role gains `users.view` in code
- Then everyone with that role, in every company, can list users
- And no data had to change

#### AT-0001-18 — My permissions come with who I am
- When I sign in
- Then the app knows my role and permissions in the company I'm working in
- And shows only what they allow

### Confirming an account

#### AT-0001-19 — A new user confirms their account
- Given I was added to "Northwind Fibre" with email "thandi@example.com"
- When I open the link in my email and set a password
- Then I am signed in to "Northwind Fibre"
- And the admins see me as "Active"

#### AT-0001-20 — Someone with an account joins another company
- Given I already use Telejects in "Blue Mast Telecom"
- And I was added to "Northwind Fibre"
- When I open the link
- Then I confirm without setting a new password
- And after signing in I can switch between both companies

#### AT-0001-21 — An invited user can't work in the company before confirming
- Given I was added but haven't opened the link
- When I try to sign in
- Then I am refused

#### AT-0001-22 — A link works once
- Given I have confirmed my account
- When I open the same link again
- Then I see "This link has already been used"

#### AT-0001-23 — A link expires
- Given my link is more than 7 days old
- When I open it
- Then I see "This link has expired. Ask your administrator for a new one."

#### AT-0001-24 — An admin resends the invitation
- Given "Thandi Nkosi" is invited
- When I resend her invitation
- Then a new email is sent
- And the link in the earlier email no longer works

#### AT-0001-25 — A weak password is refused
- When I confirm my account with the password "password"
- Then I see why it isn't accepted
- And my account stays unconfirmed

### Companies

#### AT-0001-26 — I work in one company at a time
- Given I am in "Northwind Fibre" and "Blue Mast Telecom"
- When I switch to "Blue Mast Telecom"
- Then the sidebar shows "Blue Mast Telecom"
- And nothing from "Northwind Fibre" is shown

#### AT-0001-27 — Someone in no company
- Given my only membership was removed
- When I sign in
- Then I see "You're not part of any company yet"

#### AT-0001-28 — Platform staff add a company
- When staff run `create_company "Northwind Fibre" admin@example.com`
- Then "Northwind Fibre" exists
- And its first admin is invited by email

### Keeping companies apart

#### AT-0001-29 — Another company's users are invisible
- Given "Blue Mast Telecom" has a user "Lerato Mokoena"
- When I, in "Northwind Fibre", open Users
- Then I don't see "Lerato Mokoena"
- And opening, editing, removing or resending for her by id is "not found"

#### AT-0001-30 — An admin elsewhere can't act here
- Given I am an admin of "Blue Mast Telecom" but not a member of "Northwind Fibre"
- When I send "Northwind Fibre" as my company and list, add, edit or remove users
- Then I am refused

#### AT-0001-31 — Adding a user never reveals other companies
- Given "lerato@example.com" has an account in "Blue Mast Telecom"
- When I add "lerato@example.com" to "Northwind Fibre"
- Then I see the same result as for a brand-new address
- And her name and role in the other company are not shown to me

#### AT-0001-32 — A successor can't come from another company
- Given I am the only Admin
- When I remove myself naming a user of another company as successor
- Then I see "Choose who takes over as Admin"
- And nothing changes in either company

#### AT-0001-33 — The guard rails fail when the pattern is skipped
- Given a new `/api/` route that isn't company-gated or allowlisted
- Or a new model in `apps/` that isn't a `TenantModel` or allowlisted
- Then `make test` fails

#### AT-0001-34 — A role can't come from another company
- Given "Blue Mast Telecom" has its own roles
- When I, in "Northwind Fibre", add or edit a user with one of "Blue Mast Telecom"'s role ids
- Then it is refused and nothing changes in either company
- And `/api/roles/` lists only my company's roles

#### AT-0001-35 — A query that forgets the company fails
- Given code that asks for a tenant model's rows without `in_realm`
- When it runs
- Then it raises `UnscopedQuery` instead of returning other companies' rows
- And a query scoped with `in_realm` returns only that company's rows

## Decisions
Open until Ruan approves the spec:
1. **"Company" vs "organisation" vs "workspace"** for what people see. Drafted as "company";
   code keeps `realm`.
2. **Who creates companies.** Drafted: platform staff by command, no self-sign-up yet. Is there a
   platform-staff role in the portal later (seeing all companies), or is Django admin enough?
3. **Roles.** Decided: a fixed list now, stored per company so custom roles can follow. Still
   open: are Admin, Project manager, Field technician and Viewer the right four? Should a
   Project manager be able to add Field technicians (but not Admins)? Drafted: no, only
   `users.manage` adds people.
4. **Outside people on one project.** Decided: projects never move between companies, but a
   company can let an outside person (a guest) see one specific project. See "Designed for
   later" above.
5. **Password reset** is basic for a many-company product. Drafted as out; could come straight
   after, or be pulled in here.
6. **Strict managers.** Drafted: an unscoped `TenantQuerySet` raises (stricter than
   eden-tracker, where forgetting `in_realm` returns everything). Costs an explicit
   `.across_realms()` in Django admin and the odd platform query.
7. **Mail server.** Not chosen. Without `EMAIL_URL`, mail is printed to the worker's log.

## Implementation notes

Built as approved, with the decisions as drafted (company in the UI, `realm` in code; companies
by command; four built-in roles; strict managers; password reset left for later; no mail server
chosen).

- **Tenancy (`backend/apps/realms/`):** `Realm`, `Role`, `RealmMembership`, `TenantModel`.
  `querysets.py` holds the strict `TenantQuerySet` (raises `UnscopedQuery`; scoped by `in_realm`,
  `in_realm_id`, a `realm` filter, a related manager, `none()` or `across_realms()`).
  `permissions.py` has `InRealm` (a default permission class) and `HasRealmPermission(read,
  write=)`. `access.py` has `RealmScopedViewSet` / `RealmScopedReadOnlyViewSet`,
  `RealmScopedSerializer` and `RealmScopedInputSerializer`, which narrow every related field to
  the company. `access_control.py` is the permission registry and the built-in roles.
  `admin.py` puts Django admin's `across_realms()` in one place.
- **Database guard:** migration `realms/0002` adds a composite foreign key so a membership's
  `(realm_id, role_id)` must match a role of the same company.
- **Users (`backend/apps/users/`):** `Invitation`, `services.py` (add, update, remove or cancel,
  resend, accept, `create_company`), `mail.py` and the `send-invitation-email` Hatchet task
  (carries `realm_id`), the `/api/users/` routes, and the `create_company` and `seed` commands
  (seed moved here from `accounts`).
- **Endpoints:** `/api/users/` (list, add), `/api/users/{id}/` (read, edit, remove),
  `/api/users/{id}/resend/`, `/api/roles/` and `/api/roles/{id}/` (read-only),
  `/api/users/invitations/{token}/` (public), and `/api/auth/me/` now reports the current
  company, my role and permissions, and my companies.
- **Frontend:** `src/stores/realm.ts`; `src/features/realms/` (gate, `enterRealm`, switcher,
  `usePermission`); `src/features/users/` (table with filters and search, cards at phone width;
  add/edit dialog with a role picker; remove dialog with a successor picker);
  `src/routes/_app/users/` and `src/routes/accept-invite.tsx`.
- **Tests:** scenarios 01 to 28 in `apps/users/test_users.py` (14, 17 and 35 also in
  `apps/realms/test_tenancy.py`), 29 to 34 and the guards in `apps/realms/test_isolation.py`,
  each named `test_at_0001_<nn>_...`. 104 tests in all.

Deviations and additions:
- The planned `apps/core/test_access.py` folded into the realms guard test, as specified.
- A third guard: every `.across_realms()` call outside tests is listed by file and function with
  a reason (`ACROSS_REALMS_CALLS`).
- `RealmMembership` isn't a `TenantModel` (it is the link to the realm, with its own related
  name), but its queryset is strict like the others.
- A membership's role uses `on_delete=RESTRICT`: a role in use can't be deleted on its own, but
  deleting a company removes everything.
- Cancelling an invitation is removing an invited user (same endpoint), shown as "Cancel
  invitation" in the UI.
- No company-list endpoint: `/api/auth/me/` returns my companies, which is all the switcher
  needs.
- Accepting an invitation as a new account signs the browser in to the inviting company.

Not covered by an automated test: the frontend (checked by hand in the running app in both
themes and at phone width: adding a user with a role, the emailed link through a real Hatchet
worker, confirming, switching company, permission-based hiding, the successor picker). The
Project manager's read-only view of User management was checked through the API tests only.
