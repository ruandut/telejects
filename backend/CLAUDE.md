# Backend rules

Django + DRF + SimpleJWT over ASGI (Daphne), uv for tooling. The root CLAUDE.md applies too.

## Apps

- One Django app per domain concern, under `apps/`. Platform apps (`core`, `accounts`,
  `realms`, `jobs`, `users`) hold shared plumbing and never import domain apps. Domain apps
  import downward only; `apps/core/test_architecture.py` enforces the allowed imports, so a new
  app is added there and to `INSTALLED_APPS`.
- Inside an app: `models.py`; `querysets.py`; `services.py` (writes and workflows, the only place
  that mutates models); `serializers.py`; thin `views.py`; `urls.py`; `tasks.py`; `admin.py`;
  tests next to the code as `test_*.py`. Other apps call an app's models, managers and services,
  not its views.
- When a lower app must tell a higher one something happened, it sends a Django signal from its
  own `signals.py` and the higher app connects in `AppConfig.ready` (`boards` → `automations`,
  `projects` → `boards`), so the import graph stays downward.
- Light coupling is fine where it makes sense (a queryset naming another app's relation), as long
  as the allowed imports hold. Raise any change to the import graph first.

## Queries

- Query logic lives on the model's manager, the Django way, never in a `selectors.py` module.
  Each app's `querysets.py` has a `models.QuerySet` subclass per model, and the model sets
  `objects = XQuerySet.as_manager()`. Methods are chainable: `Thing.objects.active().recent()`.
- Logic that spans more than one row (sets, aggregates, "is this name taken") goes on the
  queryset. Logic about one record goes on the model as a method or property.
- Django drops `Meta.ordering` from aggregated queries, so annotated querysets need `order_by`.

## Models

- The user model is `accounts.User`, signed in by email (stored lowercase). Always use
  `get_user_model()` or `settings.AUTH_USER_MODEL`.
- Money is `DecimalField`, never float.

## Background work (Hatchet)

- Tasks live in `apps/<app>/tasks.py` under `TASKS = [...]`; `manage.py hatchet_worker` finds
  them (`apps/jobs/registry.py`). Inputs are Pydantic models carrying ids only, always including
  `realm_id`, and the task reads with `in_realm_id(realm_id)`.
- Enqueue inside `transaction.on_commit`, through a small `_after_commit` seam tests can replace.
- Sync tasks call `close_old_connections()` around ORM work.
- Get the client from `apps.jobs.hatchet.get_hatchet()`; it is lazy so `migrate` works before a
  token exists.

## Live updates

- `config/asgi.py` routes websockets to `apps/realms/routing.py`: one events socket
  (`apps/realms/consumers.py`), whose topics each app declares in its `live.py`. A socket
  authenticates with a JWT sent as its first message and follows the API's access rules (root
  CLAUDE.md, Multi-tenancy).
- Cross-process events go over Postgres `LISTEN`/`NOTIFY` and carry ids only (`NOTIFY` payloads
  are capped at 8 KB and are not access-checked). The consumer loads what it sends through the
  owning app's scoped queryset and the same serializer as the API endpoint, for each subscriber,
  so the socket and the API always agree on who sees what and what it looks like.
- Coalesce events (about one a second per subscription) so large jobs don't flood the socket.
- Publish with `items=[...]` (even `[]`) when the topic's `render` should send data; without
  items the socket only says "changed" and the tab refetches.

## Tests

- pytest + pytest-django. `conftest.py` has `user`, `realm` (Northwind Fibre, the user its
  only Admin), `api` (signed in, in that company), `client_for(user, realm)`,
  `member(realm, email, role_key)` and `sent_token(email)` for invitation links. Invitation
  email is delivered inline to Django's test outbox.
- Company-isolation tests for every endpoint go in `apps/realms/test_isolation.py`; tests of the
  tenancy layer itself in `apps/realms/test_tenancy.py`.
- Passwords in tests come from `conftest.TEST_PASSWORD`, generated per run.
- Spec scenarios are named `test_at_<spec>_<nn>_<what>`.
