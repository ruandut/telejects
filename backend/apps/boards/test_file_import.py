"""Spec 0007: a board, or a whole project, from a monday.com export or a CSV."""

from apps.boards.models import Board
from apps.projects.test_projects import new_project, share
from apps.realms.services import create_realm
from conftest import client_for, member

# The shape of a monday.com board export (invented data): the board's name, then per group its
# name, a header row and the items, with subitems indented under their item.
MONDAY = [
    ["Acme rollout"],
    [],
    ["Gauteng"],
    ["Name", "Subitems", "Person", "Status", "Install date", "Timeline", "Fee", "Notes", "Item ID"],
    [
        "Sandton",
        "",
        "Lerato Mokoena",
        "Done",
        "2026-11-03",
        "2026-10-01 - 2026-11-03",
        "1899",
        "",
        "111",
    ],
    ["Subitems", "Name", "Owner", "Status"],
    ["", "Book survey", "", "Done"],
    [
        "Rosebank",
        "",
        "Lerato Mokoena, Tess Tester",
        "Working on it",
        "Nov 20, 2026",
        "",
        "2499.50",
        "Gate code at security",
        "112",
    ],
    [],
    ["Western Cape"],
    ["Name", "Subitems", "Person", "Status", "Install date", "Timeline", "Fee", "Notes", "Item ID"],
    ["Bellville", "", "", "Stuck", "", "", "999", "", "113"],
    ["Canal Walk", "", "Tess Tester", "Done", "2026-12-01", "", "", "", "114"],
]


def _import(api, project, rows, name=""):
    return api.post(
        "/api/boards/from-file/",
        {"project": project["id"], "name": name, "rows": rows},
        format="json",
    )


def test_at_0007_35_a_monday_export_becomes_a_board(api, realm):
    member(realm, "lerato@example.com", "project_manager", name="Lerato Mokoena")
    project = new_project(api, "Imported", template="none")
    assert api.get("/api/boards/", {"project": project["id"]}).json() == []
    res = _import(api, project, MONDAY)
    assert res.status_code == 201, res.content
    board = res.json()
    assert board["name"] == "Acme rollout"
    assert board["import"] == {"created": 4, "errors": [], "failed": 0}
    assert [g["name"] for g in board["groups"]] == ["Gauteng", "Western Cape"]
    types = {c["title"]: c["type"] for c in board["columns"]}
    assert types == {
        "Person": "people",
        "Status": "status",
        "Install date": "date",
        "Timeline": "timeline",
        "Fee": "number",
        "Notes": "text",
    }
    status = next(c for c in board["columns"] if c["title"] == "Status")
    labels = {lbl["label"]: lbl for lbl in status["settings"]["labels"]}
    assert labels["Done"]["done"] and labels["Done"]["colour"] == "green"
    assert labels["Stuck"]["colour"] == "red"
    assert board["status_column"] == status["key"]
    assert [v["kind"] for v in board["views"]] == ["table", "kanban"]
    keys = {c["title"]: c["key"] for c in board["columns"]}
    items = {i["name"]: i for i in api.get(f"/api/boards/{board['id']}/items/").json()}
    assert set(items) == {"Sandton", "Rosebank", "Bellville", "Canal Walk"}  # no subitems
    rosebank = items["Rosebank"]["values"]
    assert rosebank[keys["Install date"]] == "2026-11-20"
    assert rosebank[keys["Fee"]] == "2499.5"
    assert len(rosebank[keys["Person"]]) == 2
    assert items["Sandton"]["values"][keys["Timeline"]] == {
        "start": "2026-10-01",
        "end": "2026-11-03",
    }
    assert items["Sandton"]["done"] and not items["Bellville"]["done"]
    groups = {g["id"]: g["name"] for g in board["groups"]}
    assert groups[items["Canal Walk"]["group"]] == "Western Cape"


def test_at_0007_36_a_plain_csv_becomes_a_board(api, realm):
    project = new_project(api, "From CSV", template="none")
    rows = [
        ["Site", "Group", "Owner", "Region", "Contact email", "Website", "Live?"],
        [
            "Sandton",
            "North",
            "Someone Unknown",
            "Gauteng",
            "a@acme.example",
            "https://acme.example",
            "yes",
        ],
        ["Rosebank", "North", "", "Gauteng", "b@acme.example", "", "no"],
        ["Bellville", "South", "", "Western Cape", "", "", "yes"],
        ["Durbanville", "South", "", "Western Cape", "", "", ""],
    ]
    board = _import(api, project, rows, name="Sites").json()
    assert board["name"] == "Sites"
    assert [g["name"] for g in board["groups"]] == ["North", "South"]
    types = {c["title"]: c["type"] for c in board["columns"]}
    # Owner names nobody in the company, so it stays text rather than losing them.
    assert types == {
        "Owner": "text",
        "Region": "status",
        "Contact email": "email",
        "Website": "link",
        "Live?": "checkbox",
    }
    assert board["import"]["created"] == 4


def test_at_0007_37_importing_needs_manage_and_stays_in_the_company(api, realm):
    project = new_project(api, "Mine", template="none")
    vusi = member(realm, "vusi@example.com", "viewer")
    share(api, project["id"], vusi, "edit")
    assert _import(client_for(vusi.user, realm), project, MONDAY).status_code == 403
    other = create_realm("Blue Mast Telecom")
    outsider = client_for(member(other, "owner@example.com", "admin").user, other)
    assert _import(outsider, project, MONDAY).status_code == 404
    assert Board.objects.in_realm(realm).count() == 0
    assert _import(api, project, [["Name"]]).status_code == 400
