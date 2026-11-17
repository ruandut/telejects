"""The tenancy layer itself: strict querysets, roles and permissions (spec 0001)."""

import pytest
from django.db import IntegrityError, transaction
from django.db.models import Count

from apps.realms import access_control
from apps.realms.access_control import ADMIN, PERMISSIONS, SYSTEM_ROLES
from apps.realms.models import Realm, RealmMembership, Role
from apps.realms.querysets import UnscopedQuery
from apps.realms.services import create_realm
from apps.users.models import Invitation
from conftest import client_for, member


@pytest.fixture
def blue_mast(db):
    return create_realm("Blue Mast Telecom")


# --- AT-0001-35: a query that forgets the company fails -----------------------------------------


@pytest.mark.parametrize(
    "run",
    [
        lambda qs: list(qs),
        lambda qs: qs.count(),
        lambda qs: qs.exists(),
        lambda qs: qs.first(),
        lambda qs: qs.get(key=ADMIN),
        lambda qs: len(qs),
        lambda qs: bool(qs),
        lambda qs: qs[0],
        lambda qs: list(qs.values_list("name", flat=True)),
        lambda qs: qs.aggregate(n=Count("id")),
        lambda qs: list(qs.iterator()),
        lambda qs: qs.in_bulk(),
        lambda qs: qs.update(name="x"),
        lambda qs: qs.delete(),
        lambda qs: list(qs.filter(key=ADMIN).order_by("name")),
        lambda qs: list(qs.exclude(realm__name="x")),
    ],
)
def test_at_0001_35_a_query_that_forgets_the_company_fails(realm, run):
    with pytest.raises(UnscopedQuery):
        run(Role.objects.all())


def test_at_0001_35_a_scoped_query_returns_only_its_company(realm, blue_mast):
    assert {r.realm_id for r in Role.objects.in_realm(realm)} == {realm.id}
    assert Role.objects.in_realm(realm).count() == len(SYSTEM_ROLES)
    assert Role.objects.in_realm_id(blue_mast.id).filter(key=ADMIN).get().realm_id == blue_mast.id


def test_scoping_survives_chaining(realm, blue_mast):
    scoped = Role.objects.in_realm(realm).filter(is_system=True).exclude(key="viewer")
    assert {r.realm_id for r in scoped.order_by("name").select_related("realm")} == {realm.id}


def test_an_unscoped_query_on_memberships_fails_too(realm):
    with pytest.raises(UnscopedQuery):
        list(RealmMembership.objects.active())
    with pytest.raises(UnscopedQuery):
        Invitation.objects.count()


def test_an_id_that_isnt_one_scopes_to_nothing(realm):
    assert list(Role.objects.in_realm("1 OR 1=1")) == []
    assert list(Role.objects.in_realm(None)) == []


def test_related_objects_are_already_scoped(realm, user):
    membership = RealmMembership.objects.in_realm(realm).get(user=user)
    # Forward (base manager) and reverse (narrowed by Django) relations both work.
    assert membership.role.realm_id == realm.id
    assert list(membership.role.memberships.all()) == [membership]
    assert {m.realm_id for m in realm.memberships.all()} == {realm.id}


def test_across_realms_is_the_explicit_escape(realm, blue_mast):
    assert {r.realm_id for r in Role.objects.across_realms()} == {realm.id, blue_mast.id}


def test_deleting_a_company_takes_its_rows_with_it(realm, blue_mast):
    realm.delete()
    assert not Role.objects.in_realm(realm.id).exists()
    assert Role.objects.in_realm(blue_mast).count() == len(SYSTEM_ROLES)


# --- roles -------------------------------------------------------------------------------------


def test_at_0001_14_every_company_starts_with_the_built_in_roles(db):
    realm = create_realm("Northwind Fibre")
    roles = list(Role.objects.in_realm(realm))
    assert [r.name for r in roles] == [
        "Admin",
        "Project manager",
        "Viewer",
    ]
    assert all(r.is_system for r in roles)


def test_admin_always_has_every_permission(realm, monkeypatch):
    admin = Role.objects.in_realm(realm).by_key(ADMIN)
    assert admin.permission_set == frozenset(PERMISSIONS)
    monkeypatch.setitem(PERMISSIONS, "projects.edit", "Edit projects")
    assert "projects.edit" in admin.permission_set


@pytest.mark.parametrize(
    "key,expected",
    [
        (
            "project_manager",
            {"users.view", "integrations.view", "feasibilities.view", "feasibilities.run"},
        ),
        ("viewer", {"feasibilities.view"}),
    ],
)
def test_built_in_role_permissions(realm, key, expected):
    assert Role.objects.in_realm(realm).by_key(key).permission_set == expected


def test_at_0001_17_access_follows_permissions_not_role_names(realm, monkeypatch):
    viewer = member(realm, "viewer@example.com", "viewer").user
    client = client_for(viewer, realm)
    assert client.get("/api/users/").status_code == 403

    # A built-in role gains users.view in code. Nothing in the database changes.
    widened = access_control.SystemRole("Viewer", "Read-only access.", frozenset({"users.view"}))
    monkeypatch.setitem(SYSTEM_ROLES, "viewer", widened)
    assert client.get("/api/users/").status_code == 200


def test_custom_roles_use_their_own_list(realm):
    custom = Role.objects.create(
        realm=realm, key="auditor", name="Auditor", permissions=["users.view", "not.a.code"]
    )
    assert custom.permission_set == {"users.view"}


def test_an_unknown_permission_code_is_a_bug(realm, user):
    membership = RealmMembership.objects.in_realm(realm).get(user=user)
    with pytest.raises(KeyError):
        membership.has_perm("users.vew")


def test_at_0001_34_the_database_refuses_a_role_from_another_company(realm, blue_mast, user):
    foreign = Role.objects.in_realm(blue_mast).by_key(ADMIN)
    membership = RealmMembership.objects.in_realm(realm).get(user=user)
    membership.role = foreign
    with pytest.raises(IntegrityError), transaction.atomic():
        membership.save()
        # The constraint is deferred to the end of the transaction; check it now.
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


# --- Django admin works across companies, on purpose --------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/admin/realms/realm/",
        "/admin/realms/realm/{realm}/change/",
        "/admin/users/invitation/",
    ],
)
def test_admin_pages_load(client, realm, path):
    from django.contrib.auth import get_user_model

    staff = get_user_model().objects.create_superuser(email="staff@example.com", password=None)
    client.force_login(staff)
    assert client.get(path.format(realm=realm.id)).status_code == 200


def test_realm_itself_is_not_strict(realm):
    assert Realm.objects.count() >= 1
