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
