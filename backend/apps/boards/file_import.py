"""A board from a spreadsheet (0007): a monday.com board export, or any CSV or Excel list.

The browser reads the file and sends its rows as text. Two layouts are understood:

- **monday.com's export**: the board's name in the first row, then for each group a row with
  the group's name, a header row starting "Name", the items, and a blank row. Subitems (a
  header row starting "Subitems" and the indented rows under it) are skipped.
- **A plain list**: a header row, then one item per row. A "Group" column, if there is one,
  puts items into groups.

Each column's type is worked out from its header and its values: status (few labels, or a
header like Status, Stage or Priority), people (only when every name is someone in the
company), dates, timelines, numbers, checkboxes, emails, links, long text, else text. monday.com's
own bookkeeping columns (Item ID, Creation Log, Last Updated, Subitems) are left out. Every
value then goes through the same checks as an edit; a row that still fails is reported.
"""

import re
from collections import OrderedDict

from django.db import transaction
from rest_framework.exceptions import ValidationError

from . import services
from .column_types import COLOURS, Email, _date, _decimal
from .context import BoardContext
from .models import BoardView

MAX_ROWS = services.MAX_IMPORT_ROWS
MAX_COLUMNS = 60
SKIP_HEADERS = {"subitems", "item id", "creation log", "last updated", "item id (auto generated)"}
NAME_HEADERS = {"name", "item", "item name", "site", "site name", "title"}
STATUS_HINTS = re.compile(r"status|stage|state|priority|phase|progress", re.I)
PEOPLE_HINTS = re.compile(r"person|people|owner|assignee|assigned|responsible|team member", re.I)
DONE_WORDS = {"done", "complete", "completed", "live", "finished", "closed", "installed", "won"}
KNOWN_COLOURS = {
    "done": "green",
    "complete": "green",
    "completed": "green",
    "live": "green",
    "working on it": "amber",
    "in progress": "amber",
    "stuck": "red",
    "blocked": "red",
    "not started": "grey",
    "high": "red",
    "medium": "amber",
    "low": "blue",
}
TIMELINE = re.compile(r"^\s*(\S+(?:\s\d{1,2},\s\d{4})?)\s+[-–]\s+(\S+(?:\s\d{1,2},\s\d{4})?)\s*$")
URL = re.compile(r"^https?://\S+$", re.I)


def _cell(value) -> str:
    return "" if value is None else str(value).strip()


def _row(raw) -> list[str]:
    return [_cell(v)[:5000] for v in (raw or [])][: MAX_COLUMNS + 2]


def _filled(row) -> list[str]:
    return [c for c in row if c]


def _is_header(row) -> bool:
    return bool(row) and row[0].strip().lower() in NAME_HEADERS and len(_filled(row)) >= 1


def parse(raw_rows) -> dict:
    """{"name", "headers", "items": [{"group", "cells"}]} from the file's rows."""
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValidationError({"rows": "The file has no rows."})
    rows = [_row(r) for r in raw_rows if isinstance(r, list)]
    first_header = next((i for i, r in enumerate(rows) if _is_header(r)), None)
    singles_before = first_header is not None and any(
        len(_filled(r)) == 1 for r in rows[:first_header]
    )
    if first_header is not None and (first_header > 0 and singles_before):
        return _parse_monday(rows)
    return _parse_list(rows)


def _parse_monday(rows) -> dict:
    name = _filled(rows[0])[0] if _filled(rows[0]) else ""
    headers: list[str] = []
    items = []
    group, in_items, pending_title = None, False, None
    for row in rows[1:]:
        filled = _filled(row)
        if not filled:
            in_items = False
            continue
        if _is_header(row):
            group = pending_title or group or "Items"
            pending_title = None
            for h in row:
                if h and h not in headers:
                    headers.append(h)
            current = row
            in_items = True
            continue
        if row[0].strip().lower() == "subitems" and len(filled) > 1:
            continue  # the header of an item's subitems, which follow indented
        if not row[0].strip():
            continue  # a subitem (indented) or a summary row
        if len(filled) == 1 and not in_items:
            pending_title = filled[0]
            continue
        if in_items:
            items.append({"group": group, "cells": dict(zip(current, row, strict=False))})
        elif len(filled) == 1:
            pending_title = filled[0]
    return {"name": name, "headers": headers, "items": items}


def _parse_list(rows) -> dict:
    header_at = next((i for i, r in enumerate(rows) if _filled(r)), None)
    if header_at is None:
        raise ValidationError({"rows": "The file has no rows."})
    header = rows[header_at]
    group_col = next((h for h in header if h.strip().lower() == "group"), None)
    items = []
    for row in rows[header_at + 1 :]:
        if not _filled(row):
            continue
        cells = dict(zip(header, row, strict=False))
        items.append(
            {"group": cells.pop(group_col, "") or "Items" if group_col else "Items", "cells": cells}
        )
    headers = [h for h in header if h and h != group_col]
    return {"name": "", "headers": headers, "items": items}


# --- working out each column's type -----------------------------------------------------------


def _timeline(text):
    m = TIMELINE.match(text)
    if not m:
        return None
    start, end = _date(m.group(1)), _date(m.group(2))
    return {"start": start.isoformat(), "end": end.isoformat()} if start and end else None


def _infer(header: str, values: list[str], ctx: BoardContext) -> tuple[str, dict]:
    filled = [v for v in values if v]
    if not filled:
        return "text", {}
    lower = {v.lower() for v in filled}
    distinct = list(OrderedDict.fromkeys(filled))
    if PEOPLE_HINTS.search(header):
        names = {n.strip() for v in filled for n in v.split(",") if n.strip()}
        if names and all(ctx.person_named(n) is not None for n in names):
            return "people", {}
    if all(_timeline(v) for v in filled):
        return "timeline", {}
    if all(_date(v) for v in filled):
        return "date", {}
    if lower <= {"v", "✓", "true", "false", "yes", "no", "checked", "unchecked", "x"}:
        return "checkbox", {}
    if all(_decimal(v) is not None for v in filled):
        return "number", {}
    if all(Email.pattern.match(v) for v in filled):
        return "email", {}
    if all(URL.match(v) for v in filled):
        return "link", {}
    short = all(len(v) <= 40 for v in filled)
    if (
        short
        and len(distinct) <= 20
        and (
            STATUS_HINTS.search(header)
            or (len(distinct) <= 10 and len(filled) >= 2 * len(distinct))
        )
    ):
        labels = []
        for i, label in enumerate(distinct):
            key = label.lower()
            colour = KNOWN_COLOURS.get(key, COLOURS[(i + 1) % len(COLOURS)])
            labels.append(
                {"id": f"l{i}", "label": label, "colour": colour, "done": key in DONE_WORDS}
            )
        return "status", {"labels": labels}
    if any(len(v) > 200 or "\n" in v for v in filled):
        return "long_text", {}
    return "text", {}


def _value(kind, text):
    if not text:
        return None
    if kind == "timeline":
        return _timeline(text)
    if kind == "people":
        return [n.strip() for n in text.split(",") if n.strip()]
    return text


@transaction.atomic
def board_from_file(project, rows, name: str, actor: services.Actor) -> tuple:
    parsed = parse(rows)
    items = parsed["items"]
    if not items:
        raise ValidationError({"rows": "No items found. Check the file has a header row."})
    if len(items) > MAX_ROWS:
        raise ValidationError({"rows": f"Import at most {MAX_ROWS:,} rows at a time."})
    headers = parsed["headers"]
    name_header = next((h for h in headers if h.strip().lower() in NAME_HEADERS), headers[0])
    board = services.create_board(
        project, name or parsed["name"] or "Imported board", "_empty", actor
    )
    groups = {}
    for i, group in enumerate(OrderedDict.fromkeys(item["group"] for item in items)):
        groups[group] = services.create_group(
            board, group[:120], COLOURS[(i + 4) % len(COLOURS)]
        ).pk
    ctx = BoardContext(board, actor.membership)
    keys = {}
    for header in headers:
        if header == name_header or header.strip().lower() in SKIP_HEADERS:
            continue
        values = [item["cells"].get(header, "") for item in items]
        kind, settings = _infer(header, values, ctx)
        keys[header] = (services.create_column(board, header[:80], kind, settings).key, kind)
    status = next((key for key, kind in keys.values() if kind == "status"), "")
    due = next((key for key, kind in keys.values() if kind in ("date", "timeline")), "")
    services.update_board(board, status_column=status, due_column=due)
    if status:
        BoardView.objects.create(
            realm_id=board.realm_id,
            board=board,
            name="Kanban",
            kind=BoardView.Kind.KANBAN,
            config={"kanban_column": status},
            position=1,
        )
    rows_in = [
        {
            "name": item["cells"].get(name_header, ""),
            "group": groups[item["group"]],
            "values": {
                key: _value(kind, item["cells"].get(header, ""))
                for header, (key, kind) in keys.items()
                if item["cells"].get(header, "")
            },
        }
        for item in items
    ]
    result = services.import_rows(board, rows_in, actor)
    return board, result
