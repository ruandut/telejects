# 0007 — Projects, boards, automations and insights

- **Status:** Done
- **Depends on:** 0001
- **Django apps:** new `projects` (projects and who may work on each), `boards` (boards, groups,
  columns, items, updates, activity, views), `automations` (rules and timers), `notifications`
  (the bell), `presence` (who is on a board right now), `analytics` (charts, dashboards and the
  portfolio)
- **Touches:** frontend / backend / jobs

## Why
The company runs its rollouts in monday.com today: a project per client, a board of sites under
it, columns that change as each site moves along, and automations that react when a column
changes or a date arrives. Telejects should do that work itself, next to its feasibilities, so a
site's journey from "check feasibility" to "live" lives in one place, inside the company's own
tenancy. People outside the core team (a field contractor, later a customer) must see only the
projects they are given, and several people work on one board at the same time.

## How monday.com does it (what we keep)
- **Workspace → board → group → item → column value.** A board is a table: items are rows, grouped
  (e.g. "Gauteng", "Western Cape"), and every column has a type that decides how a value is
  edited, shown and compared.
- **Column types.** Text, long text, number, status (coloured labels, some meaning "done"),
  date, timeline, people, dropdown, checkbox, link, email, phone, location, rating, formula,
  connect boards (links items on another board), mirror (shows a column of the connected items),
  plus read-only ones (item ID, creation log, last updated).
- **Automations are recipes:** "When *trigger*, and only if *condition*, do *action*". Triggers:
  an item is created, any/a column changes, a status changes to something, an item moves to a
  group, a date arrives (with an offset: "3 days before Install date"), or every day/week at a
  time. Actions: change a column, copy a column to another, clear it, move to a group, notify
  people, create an item on another board, archive. Actions may wait ("after 2 days").
  Automation chains are capped so they can't loop.
- **Dashboards** of widgets (chart, number, battery) over one or many boards.
- **Board views** (table, kanban) saved per board, with filters and sorting.
- **Presence:** avatars of who is on the board, and which item someone is editing.
- **Updates and activity:** a conversation per item with @mentions, and a log of every change.

## Scope
- In:
  - **Projects** for a client: name, client, status (planning, active, on hold, done,
    archived), colour, dates, description, owner. Created from a template ("Site rollout" with the
    columns a rollout needs, or blank).
  - **Who may work on a project:** people with `projects.manage` (Admin, Project manager) open and
    change every project. Anyone else sees only the projects shared with them, at a level:
    **view** (read boards, dashboards, updates), **edit** (change items, add items and updates),
    **manage** (also columns, groups, views, automations, dashboards and who has access). Shared
    from the project's Access tab or from a person in User management.
  - **Boards** in a project (a first "Sites" board is made with it): groups, typed columns,
    items with values, reordering, an item drawer with every value, its updates and activity.
  - **Live, simultaneous editing:** a change to a cell reaches everyone on the board within about
    a second. Each cell is saved on its own, so two people editing different cells never overwrite
    each other. Avatars show who is on the board and a coloured ring shows the cell they're in.
  - **Saved views:** table and kanban (by any status column), with search, filters, sort and
    hidden columns.
  - **Import** sites from a CSV or Excel file into a board, mapping file columns to board columns.
  - **Automations** per board, built from the triggers, conditions and actions above, with a run
    history. Timer triggers (date arrives, every day/week) and delayed actions run on Hatchet.
  - **Notifications:** a bell with what automations and @mentions sent me, live.
  - **Insights:** a dashboard per project, and company dashboards across every project I can
    see, of widgets I build: bar, stacked bar, line, area, pie, number, with a metric (count,
    sum, average) grouped by a column, group, board, project or a date bucket.
  - **Portfolio:** every project I can see, its progress, overdue items and recent activity.
  - The menu is split into sections: Work, Providers, Company.
- Out (later specs):
  - Per-board permissions inside a project; guests from outside the company (the access model
    here is what they will use).
  - Subitems, file columns, dependencies and Gantt/timeline/calendar/map views.
  - A feasibility column or automation action that checks a site with the providers (needs the
    map spec's single-site flow first).
  - Email or WhatsApp notifications (in-app only for now).
  - Automations through the client API.

## Design notes

### Apps and imports
`projects` → `boards` → (`automations`, `presence`, `analytics`); `notifications` sits below
`automations` and `boards` (mentions). `boards` never imports `automations`: it sends Django
signals (`boards.signals`) after a change, and `automations` listens. So `boards` works, and is
tested, without rules.

### Access
- New codes: `projects.view` (use Projects, see projects shared with me; every built-in role) and
  `projects.manage` (create, archive and delete projects, share them, full access to every
  project; Admin and Project manager).
- `ProjectMember(project, membership, level)`. `Project.objects.in_realm(r).visible_to(m)` is the
  only way a project is reached; boards, items, automations and dashboards chain their own
  `visible_to(m)` (through their project) after `in_realm`, and `projects.access.level_of(m,
  project)` decides view/edit/manage. A hidden project is a 404, like another company's.
- Company dashboards and the portfolio only ever count items of visible projects.
- Mirror and connect values show only items the viewer can see; a link into a hidden project
  shows as "1 hidden item".

### Data
- Item values are one JSON object per item, keyed by column id; a column type (`column_types.py`,
  a registry like the connector definitions) validates, normalises, compares and displays its
  values. Formula, mirror, item ID, created and last-updated are computed when read.
- A cell change is `PATCH /items/<id>/values/ {column: value}`, merged under a row lock, recorded
  in the item's activity with old and new values, and published as the item's id.

### Live
- Topic `board` (subject: board) sends the changed items, built with the items serializer for
  the subscriber; structure changes say "changed" and the tab refetches.
- Topic `board_presence` (subject: board) sends who is on it: a tab heartbeats every 20 s (and
  on focusing a cell); presence older than 45 s is swept by a minutely task.
- Topic `notifications` sends my unread count.
- Every topic rechecks project visibility before each send.

### Automations
- `Automation(board, name, enabled, trigger, conditions, actions, delay)`, stored as JSON and
  validated by `automations.recipes` (the one list of triggers and actions).
- Item events run matching automations right after the change, inside the same request, each
  in its own savepoint: a failing rule is logged on its run, never fails the person's edit. Changes an
  automation makes can trigger others, up to a depth of 5.
- `automations-tick` (Hatchet, every minute): fires date-arrives and schedule triggers that are
  due (once per item per date) and delayed actions whose time has come.

### Analytics
- A widget's query is `{boards, metric, column, group_by, bucket, series_by, filters}`, computed
  over visible items only, in Python on the typed values (formulas included).

## Scenarios

### AT-0007-01 — A project manager creates a project from the rollout template
- Given I am a Project manager
- When I create "Fibre rollout" for client "Acme Retail" from the Site rollout template
- Then it has a "Sites" board with Status, Location, Assignee, Install date and the other
  rollout columns, and I am its owner

### AT-0007-02 — A viewer sees only projects shared with them
- Given two projects, one shared with Vusi (a Viewer) at view level
- When Vusi lists projects and opens the other one's board
- Then only the shared project is listed, and the other is "not found"

### AT-0007-03 — View level is read-only
- Given Vusi has view access to a project
- When he edits a cell, adds an item or adds a column
- Then each is refused and nothing changed

### AT-0007-04 — Edit level changes items but not the board's structure
- Given Vusi has edit access
- When he edits a cell and adds an item, then adds a column
- Then the cell and item are saved, and the column is refused

### AT-0007-05 — Manage level shares the project
- Given Vusi has manage access
- When he gives Thandi edit access from the Access tab
- Then Thandi sees the project

### AT-0007-06 — Access is shared from User management too
- Given I manage projects
- When I open Thandi in User management and give her view access to "Fibre rollout"
- Then she sees it, and removing it hides it again

### AT-0007-07 — Every column type keeps only valid values
- When I set a status to a label it doesn't have, a number to "abc", a date to "soon", a person
  from another company
- Then each is refused with a reason, and valid values are stored normalised

### AT-0007-08 — Two people editing different cells keep both changes
- Given Lerato and I edit the same item at once, she the Status and I the Install date
- Then the item has both values

### AT-0007-09 — A change reaches everyone on the board
- Given Lerato has the board open
- When I change a cell
- Then her board shows the new value without reloading, built for her access

### AT-0007-10 — I see who is on the board and where
- Given Lerato has the board open and is editing an item's Status
- Then I see her avatar on the board and her ring on that cell; when she leaves, it goes

### AT-0007-11 — Every change is in the item's activity
- When I change Status from "Not started" to "Survey"
- Then the item's activity shows me, the column, the old and new value

### AT-0007-12 — An @mention in an update notifies that person
- When I write an update "@Lerato please book the survey"
- Then Lerato gets a notification linking to the item, if she can see the project

### AT-0007-13 — Formula columns compute from other columns
- Given a formula "{Monthly fee} * {Term}"
- Then each item shows the product, and a blank input gives a blank result

### AT-0007-14 — Mirror shows the connected items' column, never a hidden one
- Given a Sites item connected to an Orders item, and a mirror of the order's Status
- Then I see the order's status; someone who can't see the Orders project sees "1 hidden item"

### AT-0007-15 — When a status changes to a label, change another column
- Given "When Status changes to Live, set Go-live date to today"
- When an item's Status becomes Live
- Then its Go-live date is today, and the run is in the automation's history

### AT-0007-16 — Copy a column to another when it changes
- Given "When Install date changes, copy it to Planned date"
- Then Planned date follows Install date

### AT-0007-17 — Conditions limit an automation
- Given "When Status changes, only if Region is Gauteng, notify the Assignee"
- Then only Gauteng items notify

### AT-0007-18 — Move an item to a group and notify people
- Given "When Status changes to Cancelled, move the item to Cancelled and notify Thandi"
- Then the item moves and Thandi is notified

### AT-0007-19 — Create an item on another board
- Given "When an item is created, create one on Orders with the same name"
- Then the Orders board gets the item

### AT-0007-20 — When a date arrives
- Given "3 days before Install date, notify the Assignee", and an item installing on the 23rd
- When the tick runs on the 20th after the rule's time
- Then the Assignee is notified once, however often the tick runs that day

### AT-0007-21 — After a delay
- Given "When Status changes to Survey, after 2 days, set Status to Survey overdue"
- Then nothing happens at first, and after 2 days the status changes, unless the automation
  was switched off or deleted

### AT-0007-22 — Every day or week at a time
- Given "Every Monday at 08:00, notify the Assignee of items whose Status is Stuck"
- Then on Monday's tick, Stuck items notify their assignees, once

### AT-0007-23 — Automations can't loop
- Given two automations that set each other's column
- Then the chain stops after 5 steps and the run says why

### AT-0007-24 — A failing automation never fails my edit
- Given an automation whose action can't apply (its group was deleted)
- When I change the cell
- Then my change is saved and the run is logged as failed with the reason

### AT-0007-25 — Only managers change automations
- Given Vusi has edit access
- When he creates or changes an automation
- Then it is refused; with manage access it works

### AT-0007-26 — A widget charts a board's items
- Given items with Status and Order value
- When I add a bar widget "sum of Order value by Status"
- Then it shows one bar per label with the sums, in label order

### AT-0007-27 — A line widget buckets by date
- When I add a line widget "count of items by Install date, per month"
- Then it shows one point per month in order, with empty months as zero

### AT-0007-28 — Company dashboards count only what I can see
- Given two projects, one hidden from Vusi
- When Vusi opens a company dashboard and the portfolio
- Then the hidden project's items are counted nowhere

### AT-0007-29 — The portfolio shows each project's progress
- Then each visible project shows its item count, how many are done (done labels), and how many
  are overdue (their due date passed and not done)

### AT-0007-30 — Saved views keep filters, sort and kanban column
- When I save "Stuck in Gauteng" as a kanban by Status with a filter
- Then everyone on the board sees that view and its items

### AT-0007-31 — Import sites from a file
- When I import a CSV of sites, mapping "Site" to the item name and "Lat"/"Lng" to Location
- Then the board has one item per row, with values checked like any edit, and bad rows reported

### AT-0007-32 — Another company's projects, boards and items are out of reach
- Given Blue Mast Telecom's project
- Then nothing of it appears in my lists, dashboards or portfolio, its routes are 404 for every
  method and stay unchanged, and no column, connect, people value, automation or widget can
  point into it

### AT-0007-33 — A board is made from a feasibility run
- Given a finished feasibility run of two sites
- When I add a board to a project from that run
- Then it has one item per site, named after it, with its location, a Feasibility status (the
  best answer across products), the available products, every product's answer, and the
  file's other columns; the board links back to the run

### AT-0007-34 — Only the company's runs, and only with permission to see them
- When I pick another company's run, it is refused without saying anything about it
- When someone who manages the project but can't see feasibility runs tries it, it is refused

### AT-0007-35 — A monday.com export becomes a board
- Given a monday.com board export (board name, groups, header rows, items with subitems)
- When I start a project, or add a board, from that file
- Then the board has the export's name and groups, one item per item (no subitems), and
  columns typed from their headers and values: people who are in the company, statuses with
  monday.com's colours and done labels, dates, timelines and numbers

### AT-0007-36 — A plain CSV becomes a board
- Given a list with a header row and a Group column
- Then each Group value is a group, and emails, links, checkboxes and short label sets get
  their own column types; names of people who aren't in the company stay text

### AT-0007-37 — Importing needs manage access, inside the company
- Someone with edit access, or from another company, can't import into the project

## Implementation notes

**Apps and files.**
- `apps/projects`: `Project`, `ProjectMember`; `querysets.visible_to` / `with_level`;
  `access.py` (`level_of`, `require`, `project_for`) is the one place levels are decided;
  `signals.project_created` makes the first board. Sharing from User management is
  `/api/projects/access/`.
- `apps/boards`: `Board`, `Group`, `Column` (stable `key`), `Item` (`values` JSON, `done`,
  `completed_at`, per-board `number`), `ItemUpdate`, `ItemActivity`, `BoardView`.
  `column_types.py` is the registry of 20 types; `formula.py` parses with `ast` against an
  allowlist; `context.BoardContext` computes formula, mirror, connect, item id, created and
  updated values for one viewer; `templates.py` holds the Blank and Site rollout boards;
  `signals.py` tells automations about item events. `live.py` (`board` topic) sends changed
  items built by the same `item_rows` as the API.
- `apps/automations`: `Automation`, `AutomationRun` (unique per automation, item and
  `trigger_key`, so dates and schedules fire once); `recipes.py` (triggers, operators, actions,
  validation); `services.py` (matching, actions, timers, waiting actions); `templates.py` gives
  the Site rollout board four starter rules; `tasks.automations-tick` runs every minute.
- `apps/notifications`: `Notification`, the bell's API and a `notifications` topic.
- `apps/presence`: `BoardPresence` per tab, heartbeats over the API, `board_presence` topic,
  `tasks.presence-sweep` every minute.
- `apps/analytics`: `Dashboard` (project or company), `Widget`; `query.py` runs widget queries
  and the portfolio over visible items only, by column title so company charts work across
  boards; `/api/analytics/preview/` powers the chart builder.
- `apps/core/db.same_realm` adds same-company composite foreign keys in migrations (board →
  project, group/column/view/item → board, item → group, update/activity → item, automation and
  presence → board, dashboard → project, member → project).
- `/api/auth/me/` now includes my `membership` id (boards name people by membership).
- Frontend: `features/projects`, `boards` (table with groups, sticky names, summaries, drag and
  drop, column resize; kanban; item drawer with updates and activity; filters, sort, hidden
  columns and saved views; bulk actions; CSV/XLSX import; presence avatars and editing rings),
  `automations` (sentence read-back, builder, run history), `analytics` (Recharts through the
  shadcn chart, colours from `--label-*` tokens in a fixed order checked for colour-blind
  separation in both themes), `notifications` (header bell). Routes: `/projects`,
  `/projects/$id/boards/$boardId`, `/projects/$id/insights`, `/projects/$id/access`,
  `/portfolio`. The sidebar is split into Work, Providers and Company, with projects listed
  under Projects.

- Boards from a feasibility run (`apps/boards/sources.py`): `POST /api/boards/` with
  `feasibility_run` makes a Site rollout board with Feasibility, Available products and
  Feasibility results columns plus one text column per extra file column, and one item per
  site. Needs manage on the project and `feasibilities.view`; `Board.feasibility_run` links
  back (a same-company foreign key). The values are a snapshot taken when the board is made.
  This made `boards` import `feasibilities` and `integrations` (downward).
- Boards from a file (`apps/boards/file_import.py`): `POST /api/boards/from-file/` takes the
  file's rows as text (read in the browser, `features/boards/file.ts`, CSV or XLSX) and
  recognises monday.com's export layout or a plain list, then infers each column's type. A
  project can start with no board (`template: "none"`) so a file fills it: New project → From
  a file. The hidden `_empty` template is the importer's starting point.
- Deleting a project or a board asks for its name to be typed (`ConfirmDialog
  typeToConfirm`); every other delete asks first too.

**Decisions and deviations.**
- Access is per project, not per board; boards inherit their project's level.
- Automations triggered by a change run in the same request (savepoint per rule), not on
  Hatchet: the person sees the result at once and a broken rule can't undo the edit. Timers,
  schedules and waiting actions run on Hatchet. A waiting action re-checks its conditions
  before it runs, and is cancelled if the rule is switched off or the item archived.
- Numbers are stored as exact decimal strings in the JSON values (money rule); charts sum them
  as decimals.
- Widgets and filters across boards match columns by title.
- Charts compute in Python over the boards' items; fine for thousands of items per board, a
  candidate for SQL aggregation if boards grow far larger.

**Checked on a real worker** (2026-11-20): `automations-tick` fired a date-arrives rule and a
one-minute waiting action, and `presence-sweep` removed a quiet tab. Presence and live board
updates were checked in the running app with a second user simulated through the API, not with
two real browsers.
