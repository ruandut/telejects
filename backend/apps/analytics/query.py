"""Widget queries: what a chart shows, worked out over the items a person may see (0007).

    {
      "boards": [12],                    # empty: every board in scope
      "metric": {"op": "sum", "column": "Monthly fee"},   # op: count|sum|avg|min|max
      "group_by": {"by": "column", "column": "Status"},   # by: none|column|group|board|project
                                                         #     |created|completed|done
      "bucket": "month",                 # for dates: day|week|month|quarter|year
      "series_by": {"by": "column", "column": "Region"}, # optional: one series per value
      "filters": [{"column": "Region", "op": "is", "value": "Gauteng"}],
      "limit": 12
    }

Columns are named by title, so one company widget can chart "Status" across every project's
board. Values are read through the column types (formulas and mirrors included), in Python:
boards here hold thousands of items, not millions.
"""

import datetime as dt
from collections import OrderedDict, defaultdict
from decimal import Decimal

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.boards.column_types import TYPES, type_of
from apps.boards.context import BoardContext
from apps.boards.models import Board, Group, Item

OPS = ("count", "sum", "avg", "min", "max")
BY = ("none", "column", "group", "board", "project", "created", "completed", "done")
BUCKETS = ("day", "week", "month", "quarter", "year")
DATE_TYPES = ("date", "timeline", "created", "updated")
MAX_BUCKETS = 400


def clean(config) -> dict:
    if not isinstance(config, dict):
        raise ValidationError({"config": "Describe what the widget shows."})
    metric = config.get("metric") or {"op": "count"}
    if metric.get("op") not in OPS:
        raise ValidationError({"config": "Choose count, sum, average, minimum or maximum."})
    if metric["op"] != "count" and not metric.get("column"):
        raise ValidationError({"config": "Choose the number column to add up."})

    def by(raw, field):
        raw = raw or {"by": "none"}
        if raw.get("by") not in BY:
            raise ValidationError({"config": f"Choose what to group {field} by."})
        if raw["by"] == "column" and not raw.get("column"):
            raise ValidationError({"config": "Choose the column to group by."})
        return {"by": raw["by"], "column": str(raw.get("column") or "")[:80]}

    filters = []
    for f in (config.get("filters") or [])[:10]:
        if isinstance(f, dict) and f.get("column") and f.get("op"):
            filters.append(
                {"column": str(f["column"])[:80], "op": str(f["op"]), "value": f.get("value")}
            )
    bucket = config.get("bucket") if config.get("bucket") in BUCKETS else "month"
    try:
        limit = max(1, min(int(config.get("limit") or 20), 50))
    except TypeError, ValueError:
        limit = 20
    boards = [int(b) for b in (config.get("boards") or []) if str(b).isdigit()][:50]
    return {
        "boards": boards,
        "metric": {"op": metric["op"], "column": str(metric.get("column") or "")[:80]},
        "group_by": by(config.get("group_by"), "it"),
        "series_by": by(config.get("series_by"), "series") if config.get("series_by") else None,
        "bucket": bucket,
        "filters": filters,
        "limit": limit,
        "include_archived": False,
    }


def _bucket(day: dt.date, bucket: str) -> str:
    if bucket == "day":
        return day.isoformat()
    if bucket == "week":
        return (day - dt.timedelta(days=day.weekday())).isoformat()
    if bucket == "month":
        return f"{day.year}-{day.month:02d}"
    if bucket == "quarter":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    return str(day.year)


def _next(key: str, bucket: str) -> str:
    if bucket in ("day", "week"):
        step = 1 if bucket == "day" else 7
        return (dt.date.fromisoformat(key) + dt.timedelta(days=step)).isoformat()
    if bucket == "month":
        year, month = int(key[:4]), int(key[5:7])
        return f"{year + month // 12}-{month % 12 + 1:02d}"
    if bucket == "quarter":
        year, q = int(key[:4]), int(key[-1])
        return f"{year + q // 4}-Q{q % 4 + 1}"
    return str(int(key) + 1)


def _day_of(value, column) -> dt.date | None:
    if value is None:
        return None
    if column.type == "timeline":
        return TYPES["timeline"].day(value, "start")
    if column.type in ("created", "updated"):
        at = value.get("at") if isinstance(value, dict) else None
        return dt.datetime.fromisoformat(at).date() if at else None
    return TYPES["date"].day(value)


class Scope:
    """The boards a query looks at, for one person."""

    def __init__(self, realm_id, membership, project=None, boards=()):
        rows = Board.objects.in_realm(realm_id).visible_to(membership).select_related("project")
        if project is not None:
            rows = rows.filter(project_id=project.pk)
        if boards:
            rows = rows.filter(id__in=boards)
        self.boards = list(rows.order_by("project__name", "position", "id"))
        self.membership = membership
        self.realm_id = realm_id

    def rows(self):
        """(board, context, item, values) for every live item in scope."""
        groups = {
            g.pk: g
            for g in Group.objects.in_realm(self.realm_id).filter(
                board_id__in=[b.pk for b in self.boards]
            )
        }
        for board in self.boards:
            ctx = BoardContext(board, self.membership)
            items = list(Item.objects.in_realm(self.realm_id).of_board(board).live())
            values = ctx.full_values(items)
            for item in items:
                yield board, ctx, item, values[item.pk], groups.get(item.group_id)


def _column(ctx, title):
    title = (title or "").strip().lower()
    return next((c for c in ctx.columns if c.title.strip().lower() == title), None)


def _keys(by, bucket, board, ctx, item, values, group) -> list[tuple[str, str]]:
    kind = by["by"]
    if kind == "none":
        return [("all", "All")]
    if kind == "group":
        return [(f"g:{group.name.lower()}", group.name)] if group else []
    if kind == "board":
        return [(f"b:{board.pk}", board.name)]
    if kind == "project":
        return [(f"p:{board.project_id}", board.project.name)]
    if kind == "done":
        return [("done", "Done")] if item.done else [("open", "Not done")]
    if kind == "created":
        key = _bucket(timezone.localtime(item.created_at).date(), bucket)
        return [(key, key)]
    if kind == "completed":
        if not item.completed_at:
            return []
        key = _bucket(timezone.localtime(item.completed_at).date(), bucket)
        return [(key, key)]
    column = _column(ctx, by["column"])
    if column is None:
        return []
    value = values.get(column.key)
    if column.type in DATE_TYPES:
        day = _day_of(value, column)
        if day is None:
            return []
        key = _bucket(day, bucket)
        return [(key, key)]
    return type_of(column).groups(value, column, ctx) or [("", "(blank)")]


def _is_dated(by) -> bool:
    return by["by"] in ("created", "completed")


def _passes(filters, ctx, values) -> bool:
    for f in filters:
        column = _column(ctx, f["column"])
        if column is None:
            return False
        if not type_of(column).matches(values.get(column.key), f["op"], f["value"], column, ctx):
            return False
    return True


def run(config: dict, scope: Scope) -> dict:
    """{"labels", "series": [{"key", "name", "colour", "data"}], "total", "items"}"""
    metric = config["metric"]
    group_by, series_by, bucket = config["group_by"], config["series_by"], config["bucket"]
    cells: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    labels: OrderedDict[str, str] = OrderedDict()
    series: OrderedDict[str, str] = OrderedDict()
    order: dict[str, int] = {}
    colours: dict[str, str] = {}
    dated = _is_dated(group_by)
    if "done" in (group_by["by"], (series_by or {}).get("by")):
        colours |= {"done": "green", "open": "grey"}
    counted = 0
    all_numbers: list[Decimal] = []

    for board, ctx, item, values, group in scope.rows():
        if not _passes(config["filters"], ctx, values):
            continue
        if metric["op"] == "count":
            number = Decimal(1)
        else:
            column = _column(ctx, metric["column"])
            number = type_of(column).number(values.get(column.key), column) if column else None
            if number is None:
                continue
        keys = _keys(group_by, bucket, board, ctx, item, values, group)
        if not keys:
            continue
        group_column = _column(ctx, group_by.get("column")) if group_by["by"] == "column" else None
        if group_column is not None:
            dated = dated or group_column.type in DATE_TYPES
            if group_column.type == "status":
                for i, label in enumerate(group_column.settings.get("labels", [])):
                    order.setdefault(label["label"].lower(), i)
                    colours.setdefault(label["label"].lower(), label["colour"])
        series_keys = (
            _keys(series_by, bucket, board, ctx, item, values, group)
            if series_by
            else [("all", "")]
        ) or [("", "(blank)")]
        if series_by and series_by["by"] == "column":
            series_column = _column(ctx, series_by["column"])
            if series_column is not None and series_column.type == "status":
                for label in series_column.settings.get("labels", []):
                    colours.setdefault(label["label"].lower(), label["colour"])
        counted += 1
        all_numbers.append(number)
        for key, label in keys:
            labels.setdefault(key, label)
            for skey, sname in series_keys:
                series.setdefault(skey, sname)
                cells[(key, skey)].append(number)

    def total(numbers):
        if not numbers:
            return None if metric["op"] in ("avg", "min", "max") else 0
        if metric["op"] in ("count", "sum"):
            return sum(numbers, Decimal(0))
        if metric["op"] == "avg":
            return sum(numbers, Decimal(0)) / len(numbers)
        return min(numbers) if metric["op"] == "min" else max(numbers)

    keys = list(labels)
    if dated and keys:
        keys.sort()
        filled, key = [], keys[0]
        while key <= keys[-1] and len(filled) < MAX_BUCKETS:
            filled.append(key)
            labels.setdefault(key, key)
            key = _next(key, bucket)
        keys = filled
    elif order:
        keys.sort(key=lambda k: (order.get(k, 999), labels[k].lower()))
    else:
        weight = {
            k: total([n for (g, _), ns in cells.items() if g == k for n in ns]) or 0 for k in keys
        }
        keys.sort(key=lambda k: (-weight[k], labels[k].lower()))
        if len(keys) > config["limit"]:
            keep, rest = keys[: config["limit"] - 1], keys[config["limit"] - 1 :]
            for (g, s), ns in list(cells.items()):
                if g in rest:
                    cells[("__other", s)] += ns
            labels["__other"] = "Other"
            keys = [*keep, "__other"]

    def number(value):
        return None if value is None else float(round(value, 2))

    out_series = [
        {
            "key": skey,
            "name": sname or "Total",
            "colour": colours.get(skey),
            "data": [number(total(cells.get((k, skey), []))) for k in keys],
        }
        for skey, sname in series.items()
    ] or [{"key": "all", "name": "Total", "colour": None, "data": [0 for _ in keys]}]
    return {
        "labels": [labels[k] for k in keys],
        "colours": [colours.get(k) for k in keys],
        "series": out_series,
        "total": number(total(all_numbers)),
        "items": counted,
    }


# --- the portfolio ---------------------------------------------------------------------------


def portfolio(realm_id, membership) -> dict:
    from apps.boards.models import ItemActivity
    from apps.boards.serializers import ProjectRefSerializer
    from apps.projects.models import Project

    projects = list(
        Project.objects.in_realm(realm_id)
        .visible_to(membership)
        .with_level(membership)
        .current()
        .select_related("owner__user")
        .order_by("name", "id")
    )
    scope = Scope(realm_id, membership)
    today = timezone.localdate()
    stats = {
        p.pk: {
            "boards": 0,
            "items": 0,
            "done": 0,
            "overdue": 0,
            "by_status": OrderedDict(),
            "next_due": None,
        }
        for p in projects
    }
    weeks_back = 12
    start = today - dt.timedelta(days=today.weekday()) - dt.timedelta(weeks=weeks_back - 1)
    week_keys = [(start + dt.timedelta(weeks=i)).isoformat() for i in range(weeks_back)]
    created = dict.fromkeys(week_keys, 0)
    completed = dict.fromkeys(week_keys, 0)
    seen_boards = set()
    for board, ctx, item, values, _group in scope.rows():
        s = stats.get(board.project_id)
        if s is None:
            continue
        if board.pk not in seen_boards:
            seen_boards.add(board.pk)
            s["boards"] += 1
        s["items"] += 1
        s["done"] += item.done
        status_column, due_column = ctx.status_column, ctx.due_column
        if status_column is not None:
            label = TYPES["status"].find(status_column, values.get(status_column.key))
            name, colour = (label["label"], label["colour"]) if label else ("No status", "grey")
            entry = s["by_status"].setdefault(name, {"label": name, "colour": colour, "count": 0})
            entry["count"] += 1
        if due_column is not None and not item.done:
            due = (
                _day_of(values.get(due_column.key), due_column)
                if due_column.type != "timeline"
                else TYPES["timeline"].day(values.get(due_column.key), "end")
            )
            if due is not None:
                if due < today:
                    s["overdue"] += 1
                elif s["next_due"] is None or due < s["next_due"]:
                    s["next_due"] = due
        week = _bucket(timezone.localtime(item.created_at).date(), "week")
        if week in created:
            created[week] += 1
        if item.completed_at:
            week = _bucket(timezone.localtime(item.completed_at).date(), "week")
            if week in completed:
                completed[week] += 1

    visible = [p.pk for p in projects]
    recent = (
        ItemActivity.objects.in_realm(realm_id)
        .filter(board__project_id__in=visible)
        .select_related("actor__user", "item", "board")
        .order_by("-at", "-id")[:15]
    )
    out_projects = []
    for p in projects:
        s = stats[p.pk]
        out_projects.append(
            {
                **ProjectRefSerializer(p).data,
                "status": p.status,
                "my_level": p.my_level,
                "owner_name": p.owner.display_name if p.owner_id else None,
                "end_date": p.end_date,
                "boards": s["boards"],
                "items": s["items"],
                "done": s["done"],
                "overdue": s["overdue"],
                "next_due": s["next_due"],
                "progress": round(100 * s["done"] / s["items"]) if s["items"] else 0,
                "by_status": list(s["by_status"].values()),
            }
        )
    return {
        "totals": {
            "projects": len(projects),
            "items": sum(s["items"] for s in stats.values()),
            "done": sum(s["done"] for s in stats.values()),
            "overdue": sum(s["overdue"] for s in stats.values()),
        },
        "projects": out_projects,
        "weeks": week_keys,
        "created": [created[w] for w in week_keys],
        "completed": [completed[w] for w in week_keys],
        "recent": [
            {
                "id": a.pk,
                "who": f"Automation: {a.automation_name}"
                if a.automation_id
                else (a.actor.display_name if a.actor_id else "Telejects"),
                "kind": a.kind,
                "item": a.item_id,
                "item_name": a.item.name,
                "board": a.board_id,
                "project": a.board.project_id,
                "column_title": a.column_title,
                "old_text": a.old_text,
                "new_text": a.new_text,
                "at": a.at,
            }
            for a in recent
        ],
    }
