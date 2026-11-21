"""Spec 0007: projects and who may work on each."""

from apps.projects.models import Project
from conftest import client_for, member


def new_project(api, name="Fibre rollout", template="site_rollout", **fields):
    res = api.post(
        "/api/projects/",
        {"name": name, "client": "Acme Retail", "template": template, **fields},
        format="json",
    )
    assert res.status_code == 201, res.content
    return res.json()


def first_board(api, project_id) -> dict:
    boards = api.get("/api/boards/", {"project": project_id}).json()
    return api.get(f"/api/boards/{boards[0]['id']}/").json()


def share(api, project_id, membership, level):
    res = api.post(
        f"/api/projects/{project_id}/members/",
        {"membership": membership.id, "level": level},
        format="json",
    )
    assert res.status_code == 200, res.content
    return res


def column(board, title) -> dict:
    return next(c for c in board["columns"] if c["title"] == title)


def test_at_0007_01_a_project_manager_creates_a_project_from_the_rollout_template(realm):
    pm = member(realm, "lerato@example.com", "project_manager", name="Lerato Mokoena")
    api = client_for(pm.user, realm)
    project = new_project(api)
    assert project["my_level"] == "manage"
    assert project["owner"] == pm.id and project["owner_name"] == "Lerato Mokoena"
    board = first_board(api, project["id"])
    assert board["name"] == "Sites"
    titles = [c["title"] for c in board["columns"]]
    for wanted in ("Status", "Location", "Assignee", "Install date", "Monthly fee", "Region"):
        assert wanted in titles
    assert board["status_column"] == "status" and board["due_column"] == "install"
    assert [v["kind"] for v in board["views"]] == ["table", "kanban"]
    names = [a["name"] for a in api.get("/api/automations/", {"board": board["id"]}).json()]
    assert "Stamp the go-live date" in names

    viewer = client_for(member(realm, "vusi@example.com", "viewer").user, realm)
    res = viewer.post("/api/projects/", {"name": "Mine"}, format="json")
    assert res.status_code == 403


def test_at_0007_02_a_viewer_sees_only_projects_shared_with_them(api, realm):
    vusi = member(realm, "vusi@example.com", "viewer")
    shared = new_project(api, "Shared rollout")
    hidden = new_project(api, "Hidden rollout")
    share(api, shared["id"], vusi, "view")
    his = client_for(vusi.user, realm)
    assert [p["name"] for p in his.get("/api/projects/").json()] == ["Shared rollout"]
    assert his.get(f"/api/projects/{shared['id']}/").json()["my_level"] == "view"
    hidden_board = first_board(api, hidden["id"])
    for path in (
        f"/api/projects/{hidden['id']}/",
        f"/api/boards/{hidden_board['id']}/",
        f"/api/boards/{hidden_board['id']}/items/",
    ):
        assert his.get(path).status_code == 404
    assert his.get("/api/boards/", {"project": hidden["id"]}).status_code == 404


def _add_item(client, board, name="Site A"):
    return client.post(f"/api/boards/{board['id']}/items/", {"name": name}, format="json")


def test_at_0007_03_view_level_is_read_only(api, realm):
    vusi = member(realm, "vusi@example.com", "viewer")
    project = new_project(api)
    share(api, project["id"], vusi, "view")
    board = first_board(api, project["id"])
    item = _add_item(api, board).json()
    his = client_for(vusi.user, realm)
    assert his.get(f"/api/boards/{board['id']}/items/").status_code == 200
    res = his.patch(f"/api/boards/items/{item['id']}/values/", {"status": "live"}, format="json")
    assert res.status_code == 403
    assert _add_item(his, board, "Nope").status_code == 403
    res = his.post(
        "/api/boards/columns/", {"board": board["id"], "title": "X", "type": "text"}, format="json"
    )
    assert res.status_code == 403
    assert his.post(f"/api/boards/items/{item['id']}/updates/", {"body": "hi"}).status_code == 403
    items = api.get(f"/api/boards/{board['id']}/items/").json()
    assert [i["name"] for i in items] == ["Site A"] and "status" not in items[0]["values"]


def test_at_0007_04_edit_level_changes_items_but_not_the_boards_structure(api, realm):
    vusi = member(realm, "vusi@example.com", "viewer")
    project = new_project(api)
    share(api, project["id"], vusi, "edit")
    board = first_board(api, project["id"])
    his = client_for(vusi.user, realm)
    item = _add_item(his, board).json()
    res = his.patch(
        f"/api/boards/items/{item['id']}/values/", {"status": "Survey booked"}, format="json"
    )
    assert res.status_code == 200 and res.json()["values"]["status"] == "survey"
    res = his.post(
        "/api/boards/columns/", {"board": board["id"], "title": "X", "type": "text"}, format="json"
    )
    assert res.status_code == 403
    assert (
        his.patch(f"/api/projects/{project['id']}/", {"name": "Mine"}, format="json").status_code
        == 403
    )


def test_at_0007_05_manage_level_shares_the_project(api, realm):
    vusi = member(realm, "vusi@example.com", "viewer")
    thandi = member(realm, "thandi@example.com", "viewer")
    project = new_project(api)
    share(api, project["id"], vusi, "manage")
    his = client_for(vusi.user, realm)
    hers = client_for(thandi.user, realm)
    assert hers.get("/api/projects/").json() == []
    candidates = his.get(f"/api/projects/{project['id']}/candidates/").json()
    assert thandi.id in [c["id"] for c in candidates]
    share(his, project["id"], thandi, "edit")
    assert [p["my_level"] for p in hers.get("/api/projects/").json()] == ["edit"]
    # Thandi, at edit, can't share it on.
    res = hers.post(
        f"/api/projects/{project['id']}/members/",
        {"membership": vusi.id, "level": "view"},
        format="json",
    )
    assert res.status_code == 403


def test_at_0007_06_access_is_shared_from_user_management_too(api, realm):
    thandi = member(realm, "thandi@example.com", "viewer")
    project = new_project(api)
    hers = client_for(thandi.user, realm)
    res = api.post(
        "/api/projects/access/",
        {"membership": thandi.id, "project": project["id"], "level": "view"},
        format="json",
    )
    assert res.status_code == 204
    listed = api.get("/api/projects/access/", {"membership": thandi.id}).json()
    assert listed == {
        "manages_all": False,
        "projects": [{"project": project["id"], "name": "Fibre rollout", "level": "view"}],
    }
    assert [p["name"] for p in hers.get("/api/projects/").json()] == ["Fibre rollout"]
    api.post(
        "/api/projects/access/",
        {"membership": thandi.id, "project": project["id"], "level": None},
        format="json",
    )
    assert hers.get("/api/projects/").json() == []
    # Only people who manage projects may share from User management.
    assert hers.get("/api/projects/access/", {"membership": thandi.id}).status_code == 403


def test_a_project_name_is_unique_in_the_company(api, realm):
    new_project(api, "Same")
    res = api.post("/api/projects/", {"name": "Same"}, format="json")
    assert res.status_code == 400 and "name" in res.json()
    assert Project.objects.in_realm(realm).count() == 1
