"""Spec 0007: automations, their conditions, actions, timers and limits."""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.automations import services
from apps.automations.models import AutomationRun
from apps.boards.test_boards import add, add_column, set_values
from apps.notifications.models import Notification
from apps.projects.test_projects import first_board, new_project, share
from conftest import client_for, member

SAST = ZoneInfo("Africa/Johannesburg")


@pytest.fixture
def board(api):
    return first_board(api, new_project(api, template="blank")["id"])


@pytest.fixture
def rollout(api):
    return first_board(api, new_project(api, "Rollout")["id"])


def automate(api, board, trigger, actions, **extra):
    res = api.post(
        "/api/automations/",
        {
            "board": board["id"],
            "name": extra.pop("name", "Rule"),
            "trigger": trigger,
            "actions": actions,
            **extra,
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    return res.json()


def item(api, item_id):
    return api.get(f"/api/boards/items/{item_id}/").json()


def runs(api, automation):
    return api.get(f"/api/automations/{automation['id']}/runs/").json()


def test_at_0007_15_when_a_status_changes_to_a_label_change_another_column(api, rollout):
    site = add(api, rollout)
    assert "golive" not in site["values"]
    changed = set_values(api, site, status="Live").json()
    assert changed["values"]["golive"] == timezone.localdate().isoformat()
    groups = {g["id"]: g["name"] for g in rollout["groups"]}
    assert groups[changed["group"]] == "Completed"
    rules = {a["name"]: a for a in api.get("/api/automations/", {"board": rollout["id"]}).json()}
    history = runs(api, rules["Stamp the go-live date"])
    assert [(r["status"], r["item_name"]) for r in history] == [("done", "Site A")]
    activity = api.get(f"/api/boards/items/{site['id']}/activity/").json()
    assert any(a["who"] == "Automation: Stamp the go-live date" for a in activity)


def test_at_0007_16_copy_a_column_to_another_when_it_changes(api, board):
    planned = add_column(api, board, "Planned", "date")
    automate(
        api,
        board,
        {"type": "column_changed", "column": "date"},
        [{"type": "copy_value", "from": "date", "to": planned["key"]}],
    )
    site = add(api, board)
    assert set_values(api, site, date="2026-12-01").json()["values"][planned["key"]] == "2026-12-01"
    assert set_values(api, site, date="2026-12-09").json()["values"][planned["key"]] == "2026-12-09"


def test_at_0007_17_conditions_limit_an_automation(api, realm, rollout):
    thandi = member(realm, "thandi@example.com", "project_manager")
    automate(
        api,
        rollout,
        {"type": "status_changed", "column": "status", "to": []},
        [{"type": "notify", "people_column": "assignee", "message": "{name} is now {Status}"}],
        conditions=[{"column": "region", "op": "is", "value": "Gauteng"}],
    )
    gp = add(api, rollout, "Sandton", region="Gauteng", assignee=[thandi.id])
    wc = add(api, rollout, "Bellville", region="Western Cape", assignee=[thandi.id])
    Notification.objects.in_realm(realm).delete()  # the "you were added" ones
    set_values(api, gp, status="Stuck")
    set_values(api, wc, status="Stuck")
    notes = list(Notification.objects.in_realm(realm).filter(recipient=thandi))
    assert [n.title for n in notes] == ["Sandton is now Stuck"]


def test_at_0007_18_move_an_item_to_a_group_and_notify_people(api, realm, rollout):
    thandi = member(realm, "thandi@example.com", "project_manager")
    cancelled = api.post(
        "/api/boards/groups/", {"board": rollout["id"], "name": "Cancelled"}, format="json"
    ).json()
    automate(
        api,
        rollout,
        {"type": "status_changed", "column": "status", "to": ["cancelled"]},
        [
            {"type": "move_to_group", "group": cancelled["id"]},
            {"type": "notify", "members": [thandi.id], "message": "{name} was cancelled"},
        ],
    )
    site = add(api, rollout, "Rosebank")
    assert set_values(api, site, status="Cancelled").json()["group"] == cancelled["id"]
    note = Notification.objects.in_realm(realm).get(recipient=thandi)
    assert note.title == "Rosebank was cancelled" and note.kind == "automation"


def test_at_0007_19_create_an_item_on_another_board(api, rollout):
    orders = first_board(api, new_project(api, "Orders", template="blank")["id"])
    link = add_column(api, rollout, "Order", "connect", {"board": orders["id"]})
    automate(
        api,
        rollout,
        {"type": "item_created"},
        [
            {
                "type": "create_item",
                "board": orders["id"],
                "name": "Order for {name}",
                "copy": [{"from": "install", "to": "date"}],
                "link_column": link["key"],
            }
        ],
    )
    site = add(api, rollout, "Midrand", install="2026-12-05")
    made = api.get(f"/api/boards/{orders['id']}/items/").json()
    assert [(i["name"], i["values"].get("date")) for i in made] == [
        ("Order for Midrand", "2026-12-05")
    ]
    linked = item(api, site["id"])["values"][link["key"]]["items"]
    assert [i["name"] for i in linked] == ["Order for Midrand"]


def test_at_0007_20_when_a_date_arrives(api, realm, rollout):
    thandi = member(realm, "thandi@example.com", "project_manager")
    automate(
        api,
        rollout,
        {"type": "date_arrives", "column": "install", "when": "before", "days": 3, "time": "08:00"},
        [{"type": "notify", "people_column": "assignee", "message": "{name} installs soon"}],
        name="Three days out",
    )
    add(api, rollout, "Due", install="2026-11-23", assignee=[thandi.id])
    add(api, rollout, "Later", install="2026-11-24", assignee=[thandi.id])
    Notification.objects.in_realm(realm).delete()
    early = dt.datetime(2026, 11, 20, 7, 59, tzinfo=SAST)
    services.tick(early)
    assert not Notification.objects.in_realm(realm).exists()
    for minute in (0, 1, 30):
        services.tick(dt.datetime(2026, 11, 20, 8, minute, tzinfo=SAST))
    notes = Notification.objects.in_realm(realm).filter(recipient=thandi)
    # The template's own reminder (2 days before) isn't due yet; ours fired once.
    assert [n.title for n in notes] == ["Due installs soon"]


def test_at_0007_21_after_a_delay(api, rollout):
    rule = automate(
        api,
        rollout,
        {"type": "status_changed", "column": "status", "to": ["survey"]},
        [{"type": "set_value", "column": "status", "value": "Stuck"}],
        delay={"amount": 2, "unit": "days"},
    )
    site = add(api, rollout)
    set_values(api, site, status="Survey booked")
    assert item(api, site["id"])["values"]["status"] == "survey"
    assert runs(api, rule)[0]["status"] == "scheduled"
    services.tick(timezone.now() + dt.timedelta(days=1))
    assert item(api, site["id"])["values"]["status"] == "survey"
    services.tick(timezone.now() + dt.timedelta(days=2, minutes=1))
    assert item(api, site["id"])["values"]["status"] == "stuck"
    assert runs(api, rule)[0]["status"] == "done"

    # Switched off while waiting: it never happens.
    other = add(api, rollout, "B")
    set_values(api, other, status="Survey booked")
    api.patch(f"/api/automations/{rule['id']}/", {"enabled": False}, format="json")
    services.tick(timezone.now() + dt.timedelta(days=3))
    assert item(api, other["id"])["values"]["status"] == "survey"
    assert runs(api, rule)[0]["status"] == "cancelled"


def test_at_0007_22_every_day_or_week_at_a_time(api, realm, rollout, monkeypatch):
    thandi = member(realm, "thandi@example.com", "project_manager")
    sunday = dt.datetime(2026, 11, 22, 12, 0, tzinfo=SAST)
    monkeypatch.setattr(timezone, "now", lambda: sunday)
    automate(
        api,
        rollout,
        {"type": "schedule", "every": "week", "weekday": 0, "time": "08:00"},
        [{"type": "notify", "people_column": "assignee", "message": "{name} is stuck"}],
        conditions=[{"column": "status", "op": "is", "value": "Stuck"}],
    )
    add(api, rollout, "Stuck site", status="Stuck", assignee=[thandi.id])
    add(api, rollout, "Fine site", status="Installing", assignee=[thandi.id])
    Notification.objects.in_realm(realm).delete()
    services.tick(sunday)
    services.tick(dt.datetime(2026, 11, 23, 7, 0, tzinfo=SAST))
    assert not Notification.objects.in_realm(realm).exists()
    services.tick(dt.datetime(2026, 11, 23, 8, 0, tzinfo=SAST))
    services.tick(dt.datetime(2026, 11, 23, 9, 0, tzinfo=SAST))
    titles = list(Notification.objects.in_realm(realm).values_list("title", flat=True))
    assert titles == ["Stuck site is stuck"]


def test_at_0007_23_automations_cant_loop(api, board):
    a = add_column(api, board, "A", "number")
    b = add_column(api, board, "B", "number")
    automate(
        api,
        board,
        {"type": "column_changed", "column": a["key"]},
        [{"type": "increment", "column": b["key"], "by": 1}],
        name="A to B",
    )
    rule = automate(
        api,
        board,
        {"type": "column_changed", "column": b["key"]},
        [{"type": "increment", "column": a["key"], "by": 1}],
        name="B to A",
    )
    site = add(api, board)
    res = set_values(api, site, **{a["key"]: "1"})
    assert res.status_code == 200
    values = item(api, site["id"])["values"]
    assert (values[a["key"]], values[b["key"]]) == ("3", "3")
    history = runs(api, rule)
    stopped = [r for r in history if r["status"] == "skipped"]
    assert len(stopped) == 1 and "5 times" in stopped[0]["message"]
    assert sorted(r["status"] for r in history) == ["done", "done", "skipped"]


def test_at_0007_24_a_failing_automation_never_fails_my_edit(api, board):
    doomed = api.post(
        "/api/boards/groups/", {"board": board["id"], "name": "Doomed"}, format="json"
    ).json()
    rule = automate(
        api,
        board,
        {"type": "column_changed", "column": "date"},
        [{"type": "move_to_group", "group": doomed["id"]}],
    )
    api.delete(f"/api/boards/groups/{doomed['id']}/")
    site = add(api, board)
    res = set_values(api, site, date="2026-12-01")
    assert res.status_code == 200 and res.json()["values"]["date"] == "2026-12-01"
    failed = runs(api, rule)[0]
    assert failed["status"] == "failed" and "no longer exists" in failed["message"]


def test_at_0007_25_only_managers_change_automations(api, realm, board):
    vusi = member(realm, "vusi@example.com", "viewer")
    share(api, board["project"]["id"], vusi, "edit")
    his = client_for(vusi.user, realm)
    body = {
        "board": board["id"],
        "name": "Mine",
        "trigger": {"type": "item_created"},
        "actions": [{"type": "archive_item"}],
    }
    assert his.post("/api/automations/", body, format="json").status_code == 403
    rule = automate(api, board, {"type": "item_created"}, [{"type": "archive_item"}])
    assert his.get("/api/automations/", {"board": board["id"]}).status_code == 200
    res = his.patch(f"/api/automations/{rule['id']}/", {"enabled": False}, format="json")
    assert res.status_code == 403
    assert his.delete(f"/api/automations/{rule['id']}/").status_code == 403
    share(api, board["project"]["id"], vusi, "manage")
    assert his.post("/api/automations/", body, format="json").status_code == 201


def test_rules_only_point_at_their_own_board(api, board, rollout):
    res = api.post(
        "/api/automations/",
        {
            "board": board["id"],
            "name": "x",
            "trigger": {"type": "column_changed", "column": "fee"},
            "actions": [{"type": "archive_item"}],
        },
        format="json",
    )
    assert res.status_code == 400
    res = api.post(
        "/api/automations/",
        {
            "board": board["id"],
            "name": "x",
            "trigger": {"type": "item_created"},
            "actions": [{"type": "move_to_group", "group": rollout["groups"][0]["id"]}],
        },
        format="json",
    )
    assert res.status_code == 400
    assert AutomationRun.objects.in_realm(board["project"]["id"]).count() == 0
