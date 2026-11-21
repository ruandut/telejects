"""Spec 0007: insights: widgets, dashboards and the portfolio."""

import datetime as dt

import pytest
from django.utils import timezone

from apps.boards.test_boards import add, set_values
from apps.projects.test_projects import first_board, new_project, share
from conftest import client_for, member


@pytest.fixture
def rollout(api):
    return first_board(api, new_project(api, "Rollout")["id"])


def preview(client, config, project=None):
    res = client.post(
        "/api/analytics/preview/", {"project": project, "config": config}, format="json"
    )
    assert res.status_code == 200, res.content
    return res.json()


def test_at_0007_26_a_widget_charts_a_boards_items(api, rollout):
    add(api, rollout, "A", status="Installing", fee="100")
    add(api, rollout, "B", status="Installing", fee="250.5")
    add(api, rollout, "C", status="Feasibility", fee="40")
    add(api, rollout, "D", status="Feasibility")
    project = rollout["project"]["id"]
    dashboard = api.post(
        "/api/analytics/dashboards/", {"project": project, "name": "Money"}, format="json"
    ).json()
    widget = api.post(
        "/api/analytics/widgets/",
        {
            "dashboard": dashboard["id"],
            "title": "Fees by status",
            "kind": "bar",
            "config": {
                "metric": {"op": "sum", "column": "Monthly fee"},
                "group_by": {"by": "column", "column": "Status"},
            },
        },
        format="json",
    )
    assert widget.status_code == 201
    data = api.get(f"/api/analytics/widgets/{widget.json()['id']}/data/").json()
    # Labels in the status column's own order, with their colours.
    assert data["labels"] == ["Feasibility", "Installing"]
    assert data["colours"] == ["blue", "amber"]
    assert data["series"][0]["data"] == [40.0, 350.5]
    assert data["total"] == 390.5
    counted = preview(api, {"group_by": {"by": "column", "column": "Status"}}, project)
    assert counted["series"][0]["data"] == [2, 2]


def test_at_0007_27_a_line_widget_buckets_by_date(api, rollout):
    add(api, rollout, "Jan", install="2026-01-15")
    add(api, rollout, "Jan 2", install="2026-01-20")
    add(api, rollout, "Apr", install="2026-04-02")
    data = preview(
        api,
        {"group_by": {"by": "column", "column": "Install date"}, "bucket": "month"},
        rollout["project"]["id"],
    )
    assert data["labels"] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert data["series"][0]["data"] == [2, 0, 0, 1]
    stacked = preview(
        api,
        {
            "group_by": {"by": "column", "column": "Install date"},
            "bucket": "quarter",
            "series_by": {"by": "done"},
        },
        rollout["project"]["id"],
    )
    assert stacked["labels"] == ["2026-Q1", "2026-Q2"]
    assert [s["name"] for s in stacked["series"]] == ["Not done"]


def test_at_0007_28_company_dashboards_count_only_what_i_can_see(api, realm, rollout):
    hidden = first_board(api, new_project(api, "Hidden")["id"])
    add(api, rollout, "Visible site", status="Stuck")
    for i in range(3):
        add(api, hidden, f"Secret {i}", status="Stuck")
    vusi = member(realm, "vusi@example.com", "viewer")
    share(api, rollout["project"]["id"], vusi, "view")
    his = client_for(vusi.user, realm)
    company = api.post(
        "/api/analytics/dashboards/", {"name": "Everything", "starter": True}, format="json"
    ).json()
    assert len(company["widgets"]) >= 5
    count = next(w for w in company["widgets"] if w["kind"] == "number")
    assert api.get(f"/api/analytics/widgets/{count['id']}/data/").json()["total"] == 4
    assert his.get(f"/api/analytics/widgets/{count['id']}/data/").json()["total"] == 1
    by_project = preview(his, {"group_by": {"by": "project"}})
    assert by_project["labels"] == ["Rollout"]
    portfolio = his.get("/api/analytics/portfolio/").json()
    assert [p["name"] for p in portfolio["projects"]] == ["Rollout"]
    assert portfolio["totals"]["items"] == 1
    assert "Secret" not in str(portfolio)
    # He can't build a company dashboard, nor point a widget at the hidden board.
    assert his.post("/api/analytics/dashboards/", {"name": "x"}, format="json").status_code == 403
    res = api.post(
        "/api/analytics/widgets/",
        {"dashboard": company["id"], "title": "x", "kind": "bar", "config": {"boards": [999999]}},
        format="json",
    )
    assert res.status_code == 400


def test_at_0007_29_the_portfolio_shows_each_projects_progress(api, realm, rollout):
    yesterday = (timezone.localdate() - dt.timedelta(days=1)).isoformat()
    tomorrow = (timezone.localdate() + dt.timedelta(days=1)).isoformat()
    add(api, rollout, "Live", status="Live", install=yesterday)
    add(api, rollout, "Late", status="Installing", install=yesterday)
    add(api, rollout, "Soon", status="Installing", install=tomorrow)
    add(api, rollout, "Unplanned")
    portfolio = api.get("/api/analytics/portfolio/").json()
    project = portfolio["projects"][0]
    assert (project["items"], project["done"], project["overdue"], project["progress"]) == (
        4,
        1,
        1,
        25,
    )
    assert project["next_due"] == tomorrow
    statuses = {s["label"]: s["count"] for s in project["by_status"]}
    assert statuses == {"Live": 1, "Installing": 2, "No status": 1}
    assert portfolio["totals"] == {"projects": 1, "items": 4, "done": 1, "overdue": 1}
    assert sum(portfolio["completed"]) == 1 and sum(portfolio["created"]) == 4
    assert portfolio["recent"][0]["item_name"]


def test_formula_and_mirror_values_can_be_charted(api, rollout):
    item = add(api, rollout, "A", fee="100", term="12")
    set_values(api, item, status="Ordered")
    data = preview(
        api, {"metric": {"op": "sum", "column": "Contract value"}}, rollout["project"]["id"]
    )
    assert data["total"] == 1200.0
