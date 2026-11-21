"""Spec 0007: boards, items, column types, activity, updates, views and imports."""

import threading

import pytest
from django.db import connection

from apps.boards.models import Item
from apps.notifications.models import Notification
from apps.projects.test_projects import column, first_board, new_project, share
from apps.realms.services import create_realm
from conftest import client_for, member


@pytest.fixture
def board(api):
    project = new_project(api)
    return first_board(api, project["id"])


def add(api, board, name="Site A", **values):
    res = api.post(
        f"/api/boards/{board['id']}/items/", {"name": name, "values": values}, format="json"
    )
    assert res.status_code == 201, res.content
    return res.json()


def set_values(api, item, **values):
    return api.patch(f"/api/boards/items/{item['id']}/values/", values, format="json")


def add_column(api, board, title, kind, settings=None):
    res = api.post(
        "/api/boards/columns/",
        {"board": board["id"], "title": title, "type": kind, "settings": settings or {}},
        format="json",
    )
    assert res.status_code == 201, res.content
    return res.json()


def test_at_0007_07_every_column_type_keeps_only_valid_values(api, realm, board):
    item = add(api, board)
    other = member(create_realm("Blue Mast Telecom"), "olu@example.com", "admin")
    bad = {
        "status": "Teleported",
        "fee": "abc",
        "install": "soon",
        "assignee": [other.id],
        "email": "not-an-email",
        "location": {"lat": 120, "lng": 28},
        "region": ["Atlantis"],
        "contract": "5",
    }
    for key, value in bad.items():
        res = set_values(api, item, **{key: value})
        assert res.status_code == 400, key
        assert key in res.json()["values"]
    me = member(realm, "tester@example.com", "admin")
    res = set_values(
        api,
        item,
        status="installing",
        fee="1 299.5",
        install="23/11/2026",
        assignee=[me.id],
        email="Site@Example.com",
        location="-26.1, 28.05",
        region="Gauteng",
        term=24,
    )
    assert res.status_code == 200, res.content
    values = res.json()["values"]
    assert values["status"] == "install"
    assert values["fee"] == "1299.5"
    assert values["install"] == "2026-11-23"
    assert values["assignee"] == [me.id]
    assert values["email"] == "site@example.com"
    assert values["location"] == {"address": "", "lat": -26.1, "lng": 28.05}
    assert values["region"] == ["o0"]
    # Blank clears the value.
    assert "fee" not in set_values(api, item, fee="").json()["values"]


@pytest.mark.django_db(transaction=True)
def test_at_0007_08_two_people_editing_different_cells_keep_both_changes():
    from apps.realms.access_control import ADMIN
    from apps.realms.services import add_member
    from conftest import make_user

    realm = create_realm("Northwind Fibre")
    me = make_user("tester@example.com")
    add_member(realm, me, ADMIN)
    lerato = member(realm, "lerato@example.com", "project_manager")
    mine, hers = client_for(me, realm), client_for(lerato.user, realm)
    board = first_board(mine, new_project(mine)["id"])
    item = add(mine, board)
    results = []

    def edit(client, values):
        results.append(set_values(client, item, **values).status_code)
        connection.close()

    threads = [
        threading.Thread(target=edit, args=(hers, {"status": "Stuck"})),
        threading.Thread(target=edit, args=(mine, {"install": "2026-12-01"})),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200, 200]
    values = Item.objects.in_realm(realm).get(pk=item["id"]).values
    assert values["status"] == "stuck" and values["install"] == "2026-12-01"


def test_at_0007_11_every_change_is_in_the_items_activity(api, board):
    item = add(api, board, status="Not started")
    set_values(api, item, status="Survey booked")
    activity = api.get(f"/api/boards/items/{item['id']}/activity/").json()
    change = activity[0]
    assert change["kind"] == "value"
    assert change["who"] == "Tess Tester"
    assert (change["column_title"], change["old_text"], change["new_text"]) == (
        "Status",
        "Not started",
        "Survey booked",
    )
    assert activity[-1]["kind"] == "created"


def test_at_0007_12_an_at_mention_notifies_that_person(api, realm, board):
    lerato = member(realm, "lerato@example.com", "project_manager", name="Lerato Mokoena")
    vusi = member(realm, "vusi@example.com", "viewer")  # can't see the project
    item = add(api, board)
    res = api.post(
        f"/api/boards/items/{item['id']}/updates/",
        {"body": "@Lerato please book the survey", "mentions": [lerato.id, vusi.id]},
        format="json",
    )
    assert res.status_code == 201
    assert res.json()["mentions"] == [lerato.id]
    hers = client_for(lerato.user, realm).get("/api/notifications/").json()
    assert hers["unread"] == 1
    note = hers["results"][0]
    assert note["kind"] == "mention" and note["link"]["item"] == item["id"]
    assert "Tess Tester mentioned you" in note["title"]
    assert Notification.objects.in_realm(realm).filter(recipient=vusi).count() == 0
    read = client_for(lerato.user, realm).post("/api/notifications/read/", {}, format="json")
    assert read.json() == {"unread": 0}


def test_at_0007_13_formula_columns_compute_from_other_columns(api, board):
    item = add(api, board, fee="1000", term="24")
    assert item["values"]["contract"] == "24000"
    blank = add(api, board, "No fee", term="24")
    assert blank["values"]["contract"] is None
    days = add_column(
        api, board, "Lead time", "formula", {"expression": "DAYS({Ordered}, {Install date})"}
    )
    timed = set_values(api, item, ordered="2026-11-01", install="2026-11-21").json()
    assert timed["values"][days["key"]] == "20"
    res = api.post(
        "/api/boards/columns/",
        {
            "board": board["id"],
            "title": "Bad",
            "type": "formula",
            "settings": {"expression": "__import__('os')"},
        },
        format="json",
    )
    assert res.status_code == 400


def test_at_0007_14_mirror_shows_the_connected_items_column_never_a_hidden_one(api, realm, board):
    orders_project = new_project(api, "Orders", template="blank")
    orders = first_board(api, orders_project["id"])
    order = add(api, orders, "PO-1001", status="Done")
    link = add_column(api, board, "Order", "connect", {"board": orders["id"]})
    mirror = add_column(
        api,
        board,
        "Order status",
        "mirror",
        {"connect_column": link["key"], "target_column": "status"},
    )
    item = add(api, board, "Site A")
    res = set_values(api, item, **{link["key"]: [order["id"]]})
    values = res.json()["values"]
    assert values[link["key"]]["items"][0]["name"] == "PO-1001"
    assert values[mirror["key"]]["items"][0]["text"] == "Done"

    vusi = member(realm, "vusi@example.com", "viewer")
    share(api, board["project"]["id"], vusi, "view")
    his = client_for(vusi.user, realm).get(f"/api/boards/{board['id']}/items/").json()
    seen = next(i for i in his if i["id"] == item["id"])["values"]
    assert seen[link["key"]] == {"items": [], "hidden": 1}
    assert seen[mirror["key"]] == {"items": [], "hidden": 1}
    assert "PO-1001" not in str(his)


def test_at_0007_30_saved_views_keep_filters_sort_and_kanban_column(api, realm, board):
    config = {
        "kanban_column": "status",
        "filters": [{"column": "region", "op": "is", "value": "Gauteng"}],
        "sort": [{"column": "install", "dir": "asc"}],
        "hidden": ["notes"],
    }
    res = api.post(
        "/api/boards/views/",
        {"board": board["id"], "name": "Stuck in Gauteng", "kind": "kanban", "config": config},
        format="json",
    )
    assert res.status_code == 201
    lerato = member(realm, "lerato@example.com", "project_manager")
    views = client_for(lerato.user, realm).get(f"/api/boards/{board['id']}/").json()["views"]
    saved = next(v for v in views if v["name"] == "Stuck in Gauteng")
    assert saved["kind"] == "kanban" and saved["config"] == config
    res = api.post(
        "/api/boards/views/",
        {"board": board["id"], "name": "Bad", "kind": "kanban", "config": {"kanban_column": "fee"}},
        format="json",
    )
    assert res.status_code == 400


def test_at_0007_31_import_sites_from_a_file(api, board):
    rows = [
        {
            "name": "Site 1",
            "values": {"location": {"lat": "-26.1", "lng": "28.0"}, "status": "Feasibility"},
        },
        {"name": "Site 2", "values": {"location": "-25.7, 28.2", "fee": "oops"}},
        {"name": "", "values": {}},
        {"name": "Site 4", "values": {"region": "Western Cape"}},
    ]
    res = api.post(f"/api/boards/{board['id']}/import/", {"rows": rows}, format="json")
    body = res.json()
    assert res.status_code == 200
    assert body["created"] == 2 and body["failed"] == 2
    assert [e["row"] for e in body["errors"]] == [2, 3]
    assert "fee" in body["errors"][0]["errors"]["values"]
    items = api.get(f"/api/boards/{board['id']}/items/").json()
    assert [i["name"] for i in items] == ["Site 1", "Site 4"]
    assert items[0]["values"]["location"]["lat"] == -26.1


def test_groups_columns_and_items_move_and_archive(api, board):
    group = api.post(
        "/api/boards/groups/", {"board": board["id"], "name": "Cape Town"}, format="json"
    ).json()
    a, b = add(api, board, "A"), add(api, board, "B")
    moved = api.patch(f"/api/boards/items/{b['id']}/", {"group": group["id"]}, format="json").json()
    assert moved["group"] == group["id"]
    api.post(f"/api/boards/items/{a['id']}/archive/")
    assert [i["name"] for i in api.get(f"/api/boards/{board['id']}/items/").json()] == ["B"]
    archived = api.get(f"/api/boards/{board['id']}/items/", {"archived": "1"}).json()
    assert [i["name"] for i in archived] == ["A"]
    col = add_column(api, board, "Temp", "text")
    set_values(api, moved, **{col["key"]: "hello"})
    api.delete(f"/api/boards/columns/{col['id']}/")
    assert col["key"] not in api.get(f"/api/boards/items/{b['id']}/").json()["values"]


def test_done_follows_the_status_columns_done_labels(api, board):
    item = add(api, board, status="Live")
    assert item["done"] is True
    assert set_values(api, item, status="Stuck").json()["done"] is False


# --- a board made from a feasibility run -------------------------------------------------------


def _demo_run(api, sites, name="Branch rollout"):
    from apps.integrations.models import ProviderProduct
    from conftest import connect

    connect(api, "demo", "Demo")
    products = list(ProviderProduct.objects.in_realm(api.realm).values_list("id", flat=True))
    res = api.post(
        "/api/feasibilities/runs/",
        {
            "name": name,
            "products": products,
            "rows": [
                {
                    "line_number": i + 2,
                    "name": site,
                    "latitude": lat,
                    "longitude": lng,
                    "row": {"Site": site, "Lat": str(lat), "Lng": str(lng), "Ref": f"R-{i}"},
                }
                for i, (site, lat, lng) in enumerate(sites)
            ],
            "columns": ["Site", "Lat", "Lng", "Ref"],
            "mapping": {"name": "Site", "latitude": "Lat", "longitude": "Lng"},
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    return res.json()


def test_at_0007_33_a_board_is_made_from_a_feasibility_run(api, realm, connectors):
    api.realm = realm
    run = _demo_run(api, [("Sandton", -26.1, 28.05), ("Bellville", -33.9, 18.63)])
    project = new_project(api, "From feasibility")
    res = api.post(
        "/api/boards/",
        {"project": project["id"], "name": "Feasible sites", "feasibility_run": run["id"]},
        format="json",
    )
    assert res.status_code == 201, res.content
    board = res.json()
    assert board["feasibility_run"] == {"id": run["id"], "name": "Branch rollout"}
    titles = [c["title"] for c in board["columns"]]
    for wanted in ("Feasibility", "Available products", "Feasibility results", "Ref", "Status"):
        assert wanted in titles
    keys = {c["title"]: c["key"] for c in board["columns"]}
    items = api.get(f"/api/boards/{board['id']}/items/").json()
    assert [i["name"] for i in items] == ["Sandton", "Bellville"]
    sandton = items[0]["values"]
    assert sandton["location"]["lat"] == -26.1 and sandton["location"]["lng"] == 28.05
    assert sandton[keys["Ref"]] == "R-0"
    assert sandton[keys["Feasibility"]] in {"available", "near_net", "coverage", "not_avail"}
    assert "Demo: Demo" in sandton[keys["Feasibility results"]]
    feasibility = column(board, "Feasibility")
    if sandton[keys["Feasibility"]] == "available":
        assert sandton[keys["Available products"]]
    assert [lbl["label"] for lbl in feasibility["settings"]["labels"]][-1] == "Pending"
    listed = api.get("/api/boards/", {"project": project["id"]}).json()
    assert [b["feasibility_run"] for b in listed] == [None, run["id"]]


def test_at_0007_34_only_the_companys_runs_and_with_permission(api, realm, connectors, monkeypatch):
    from apps.realms import access_control

    api.realm = realm
    project = new_project(api, "Mine")
    other = create_realm("Blue Mast Telecom")
    owner = member(other, "owner@example.com", "admin")
    theirs_api = client_for(owner.user, other)
    theirs_api.realm = other
    theirs = _demo_run(theirs_api, [("Blue Depot", -25.7, 28.2)], name="Blue run")
    res = api.post(
        "/api/boards/", {"project": project["id"], "feasibility_run": theirs["id"]}, format="json"
    )
    assert res.status_code == 400 and "Blue" not in res.content.decode()
    mine = _demo_run(api, [("Sandton", -26.1, 28.05)])
    # Managing the project isn't enough without seeing feasibility runs.
    vusi = member(realm, "vusi@example.com", "viewer")
    share(api, project["id"], vusi, "manage")
    viewer = access_control.SYSTEM_ROLES["viewer"]
    monkeypatch.setitem(
        access_control.SYSTEM_ROLES,
        "viewer",
        access_control.SystemRole(viewer.name, viewer.description, frozenset({"projects.view"})),
    )
    res = client_for(vusi.user, realm).post(
        "/api/boards/", {"project": project["id"], "feasibility_run": mine["id"]}, format="json"
    )
    assert res.status_code == 403


def test_every_feasibility_answer_has_a_label(api, realm):
    """Each provider answer, and none yet, maps to a label the Feasibility column holds."""
    from apps.boards import sources
    from apps.boards.column_types import TYPES
    from apps.integrations.canonical import Status

    kept = TYPES["status"].clean_settings({"labels": sources.LABELS})["labels"]
    assert [lbl["id"] for lbl in kept] == [lbl["id"] for lbl in sources.LABELS]
    for status in Status:
        assert sources.LABEL_IDS[status] in {lbl["id"] for lbl in kept}
