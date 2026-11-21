# Specs

Every feature starts as one file here: `NNNN-short-name.md`, copied from
[`_TEMPLATE.md`](_TEMPLATE.md). Ruan writes or approves it, then it gets built.

## Lifecycle

`Draft` → `Approved` → `In progress` → `Done`

A spec is Done when every scenario has a passing test named `test_at_<spec>_<nn>_<what>`, every
new endpoint has its company-isolation tests, and `make test` and `make check` pass.

## Writing good scenarios

- From the user's point of view: "When I open the dashboard", not "When I GET".
- One behaviour per scenario, named after the rule it proves.
- Observable outcomes: what the user sees, not which task ran.
- Say who is acting whenever access matters.
- Invented data only.

## Index

| Spec | Title | Status |
|---|---|---|
| [0001](0001-user-management.md) | Companies and user management | Done |
| [0002](0002-my-settings.md) | My settings: changing my password | Done |
| [0003](0003-integrations-feasibilities.md) | Integrations and bulk feasibilities | Done |
| [0004](0004-platform-provider-accounts.md) | Telejects' provider accounts, shared with chosen companies | Done |
| [0005](0005-integration-request-logs.md) | Integration request logs | Done |
| [0006](0006-price-book-and-quotes.md) | Telejects' price book and single-site quotes over the API | Done |
| [0007](0007-projects-boards-automations.md) | Projects, boards, automations and insights | Done |
