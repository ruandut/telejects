"""Query logic for companies (realms), and the strict base every company-owned queryset builds on.

Each model sets `objects = <Model>QuerySet.as_manager()`, so reads chain from the model with the
company first: `Role.objects.in_realm(realm).system()`.

A TenantQuerySet refuses to run until it is scoped to a company. Iterating, counting, fetching,
aggregating, updating or deleting an unscoped one raises UnscopedQuery, so forgetting
`in_realm` fails loudly instead of quietly returning every company's rows. A queryset counts as
scoped when:
- `in_realm(realm)` / `in_realm_id(id)` was called (the normal way);
- it filters on `realm` / `realm_id` (Django's own uniqueness checks and `get_or_create` do);
- it comes from a related object (`realm.memberships`), which Django already narrows;
- it is empty (`none()`);
- `across_realms()` was called. That is the explicit escape for platform-wide work, and every
  call site is allowlisted with a reason in test_isolation.py.

Forward relations (`membership.role`) and deletes use Django's plain base manager, which is safe
because they start from a row that was already reached through a scoped query.
"""

from django.db import models
from django.db.models import Count, Q

REALM_KEYS = {"realm", "realm_id", "realm__id", "realm__pk"}


class UnscopedQuery(RuntimeError):
    """A company-owned queryset ran without being scoped to a company."""


def _as_id(value) -> int | None:
    """An id from a model instance, an int or a string; None for anything that isn't one."""
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


class TenantQuerySet(models.QuerySet):
    """For models with a `realm` foreign key. Unscoped use raises UnscopedQuery."""

    _realm_scoped = False

    # --- scoping ----------------------------------------------------------------------------

    def in_realm(self, realm):
        """Rows of that company (a Realm or its id). Nothing for a value that isn't an id."""
        realm_id = _as_id(realm)
        clone = self.none() if realm_id is None else self.filter(realm_id=realm_id)
        clone._realm_scoped = True
        return clone

    def in_realm_id(self, realm_id):
        """The same as in_realm, named for Hatchet tasks, which carry an id."""
        return self.in_realm(realm_id)

    def across_realms(self):
        """Every company's rows. Only for platform-wide work; allowlisted per call site."""
        clone = self._chain()
        clone._realm_scoped = True
        return clone

    def by_id(self, pk):
        """That row, or None (also for a value that isn't an id). Chain it after in_realm."""
        pk = _as_id(pk)
        return None if pk is None else self.filter(pk=pk).first()

    # --- the guard --------------------------------------------------------------------------

    def _clone(self):
        clone = super()._clone()
        clone._realm_scoped = self._realm_scoped
        return clone

    def _filter_or_exclude(self, negate, args, kwargs):
        clone = super()._filter_or_exclude(negate, args, kwargs)
        if not negate and any(k in REALM_KEYS and v is not None for k, v in kwargs.items()):
            clone._realm_scoped = True
        return clone

    def _check_scoped(self):
        if self._realm_scoped or self._hints.get("instance") is not None:
            return
        if self.query.is_empty():
            return
        raise UnscopedQuery(
            f"{self.model.__name__} rows were queried without a company. Start the query with "
            f"{self.model.__name__}.objects.in_realm(realm)."
        )

    def _fetch_all(self):
        if self._result_cache is None:
            self._check_scoped()
        super()._fetch_all()

    def iterator(self, *args, **kwargs):
        self._check_scoped()
        return super().iterator(*args, **kwargs)

    def count(self):
        self._check_scoped()
        return super().count()

    def exists(self):
        self._check_scoped()
        return super().exists()

    def contains(self, obj):
        self._check_scoped()
        return super().contains(obj)

    def aggregate(self, *args, **kwargs):
        self._check_scoped()
        return super().aggregate(*args, **kwargs)

    def in_bulk(self, *args, **kwargs):
        self._check_scoped()
        return super().in_bulk(*args, **kwargs)

    def update(self, **kwargs):
        self._check_scoped()
        return super().update(**kwargs)

    def delete(self):
        self._check_scoped()
        return super().delete()

    def explain(self, **options):
        self._check_scoped()
        return super().explain(**options)


class RealmQuerySet(models.QuerySet):
    """Companies themselves. Not company-owned, so not strict; reach them through memberships."""

    def of_user(self, user):
        """The companies the user is an active member of."""
        from .models import RealmMembership  # models.py imports this module

        return self.filter(
            memberships__user=user, memberships__status=RealmMembership.Status.ACTIVE
        ).order_by("name", "id")


class RoleQuerySet(TenantQuerySet):
    def system(self):
        return self.filter(is_system=True)

    def by_key(self, key):
        return self.filter(key=key).first()

    def with_member_count(self):
        from .models import RealmMembership  # models.py imports this module

        current = [RealmMembership.Status.ACTIVE, RealmMembership.Status.INVITED]
        return self.annotate(
            member_count=Count("memberships", filter=Q(memberships__status__in=current))
        ).order_by("position", "name", "id")


class RealmMembershipQuerySet(TenantQuerySet):
    def active(self):
        return self.filter(status=self.model.Status.ACTIVE)

    def current(self):
        """Everyone User management lists: people with access, and people asked to join."""
        return self.filter(status__in=[self.model.Status.ACTIVE, self.model.Status.INVITED])

    def admins(self):
        from .access_control import ADMIN

        return self.filter(role__is_system=True, role__key=ADMIN)

    def of_user(self, user):
        """The user's own active memberships, in every company, with company and role.

        Across companies by design: it is how a request finds which companies the user may work
        in, and it only ever returns the user's own rows.
        """
        return (
            self.across_realms()
            .filter(user=user)
            .active()
            .select_related("realm", "role")
            .order_by("realm__name", "realm_id")
        )

    def default_for(self, user):
        """The company a request works in when it doesn't name one: the user's oldest."""
        return self.of_user(user).order_by("id").first()

    def people(self):
        """The company's current people, as User management lists them."""
        return self.current().select_related("user", "role").order_by("name", "user__email", "id")
