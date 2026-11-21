"""What an automation can do: the one list of triggers, condition operators and actions, and
the checks that keep a rule pointing only at its own board's columns and groups (or a board the
author may edit) (0007).

    trigger     {"type": "status_changed", "column": "status", "to": ["live"]}
    conditions  [{"column": "region", "op": "is", "value": "o0"}]
    actions     [{"type": "set_value", "column": "golive", "value": {"today_plus": 0}}]
    delay       {"amount": 2, "unit": "days"}
"""

import re
from datetime import timedelta

from rest_framework.exceptions import ValidationError

from apps.boards.column_types import TYPES, Invalid, type_of
from apps.boards.context import BoardContext
from apps.boards.models import Board, Group
from apps.projects.access import can
from apps.realms.models import RealmMembership

TRIGGERS = {
    "item_created": "When an item is created",
    "column_changed": "When a column changes",
    "status_changed": "When a status changes to something",
    "item_moved": "When an item moves to a group",
    "date_arrives": "When a date arrives",
    "schedule": "Every day, week or month at a time",
}
TIMER_TRIGGERS = {"date_arrives", "schedule"}

OPERATORS = {
    "is": "is",
    "is_not": "is not",
    "is_empty": "is empty",
    "is_not_empty": "is not empty",
    "contains": "contains",
    "gt": "is greater than",
    "lt": "is less than",
    "gte": "is at least",
    "lte": "is at most",
}

ACTIONS = {
    "set_value": "Set a column",
    "clear_value": "Clear a column",
    "copy_value": "Copy a column to another",
    "increment": "Add to a number",
    "move_to_group": "Move the item to a group",
    "notify": "Notify people",
    "create_item": "Create an item on a board",
    "archive_item": "Archive the item",
}

DELAY_UNITS = {
    "minutes": timedelta(minutes=1),
    "hours": timedelta(hours=1),
    "days": timedelta(days=1),
}
MAX_ACTIONS = 10
MAX_DEPTH = 5
TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def catalogue() -> dict:
    return {
        "triggers": TRIGGERS,
        "operators": OPERATORS,
        "actions": ACTIONS,
        "delay_units": list(DELAY_UNITS),
        "max_depth": MAX_DEPTH,
    }


class Checker:
    def __init__(self, board: Board, membership: RealmMembership | None):
        self.board = board
        self.membership = membership
        self.ctx = BoardContext(board, membership)
        self.groups = set(
            Group.objects.in_realm(board.realm_id).of_board(board).values_list("id", flat=True)
        )

    def fail(self, field, message):
        raise ValidationError({field: message})

    def column(self, field, key, types=None, writable=False, allow_name=False):
        if allow_name and key == "name":
            return None
        column = self.ctx.by_key.get(key)
        if column is None:
            self.fail(field, "Choose one of this board's columns.")
        if types and column.type not in types:
            self.fail(
                field, f"Choose a {' or '.join(TYPES[t].label.lower() for t in types)} column."
            )
        if writable and TYPES[column.type].computed:
            self.fail(field, f"{column.title} is worked out by itself, so it can't be set.")
        return column

    def time(self, field, value):
        if not isinstance(value, str) or not TIME.match(value):
            self.fail(field, "Choose a time, like 08:00.")
        return value

    # --- trigger --------------------------------------------------------------------------

    def trigger(self, raw) -> dict:
        if not isinstance(raw, dict) or raw.get("type") not in TRIGGERS:
            self.fail("trigger", "Choose what sets it off.")
        kind = raw["type"]
        out = {"type": kind}
        if kind == "column_changed":
            out["column"] = (
                None
                if raw.get("column") in (None, "")
                else self.column("trigger", raw["column"]).key
            )
        elif kind == "status_changed":
            column = self.column("trigger", raw.get("column"), ["status"])
            labels = {label["id"] for label in column.settings.get("labels", [])}
            to = [t for t in raw.get("to") or [] if t in labels]
            if len(to) != len(raw.get("to") or []):
                self.fail("trigger", "Choose labels of that status column.")
            out |= {"column": column.key, "to": to}
        elif kind == "item_moved":
            group = raw.get("group")
            if group is not None and group not in self.groups:
                self.fail("trigger", "Choose one of this board's groups.")
            out["group"] = group
        elif kind == "date_arrives":
            column = self.column("trigger", raw.get("column"), ["date", "timeline"])
            when = raw.get("when") if raw.get("when") in ("before", "on", "after") else "on"
            try:
                days = int(raw.get("days") or 0)
            except TypeError, ValueError:
                self.fail("trigger", "Choose how many days.")
            if not 0 <= days <= 365:
                self.fail("trigger", "Choose 0 to 365 days.")
            out |= {
                "column": column.key,
                "when": when,
                "days": 0 if when == "on" else days,
                "time": self.time("trigger", raw.get("time") or "08:00"),
            }
        elif kind == "schedule":
            every = raw.get("every")
            if every not in ("day", "weekday", "week", "month"):
                self.fail("trigger", "Choose every day, weekday, week or month.")
            out |= {"every": every, "time": self.time("trigger", raw.get("time") or "08:00")}
            if every == "week":
                weekday = raw.get("weekday")
                if weekday not in range(7):
                    self.fail("trigger", "Choose a day of the week.")
                out["weekday"] = weekday
            if every == "month":
                day = raw.get("day")
                if day not in range(1, 29):
                    self.fail("trigger", "Choose a day from 1 to 28.")
                out["day"] = day
        return out

    # --- conditions -----------------------------------------------------------------------

    def conditions(self, raw) -> list:
        if raw in (None, ""):
            return []
        if not isinstance(raw, list) or len(raw) > 10:
            self.fail("conditions", "Add up to 10 conditions.")
        out = []
        for condition in raw:
            if not isinstance(condition, dict) or condition.get("op") not in OPERATORS:
                self.fail("conditions", "Choose how each condition compares.")
            if condition.get("column") == "group":
                if condition.get("value") not in self.groups or condition["op"] not in (
                    "is",
                    "is_not",
                ):
                    self.fail("conditions", "Choose one of this board's groups.")
                out.append({"column": "group", "op": condition["op"], "value": condition["value"]})
                continue
            column = self.column("conditions", condition.get("column"))
            value = condition.get("value")
            if isinstance(value, str):
                value = value[:200]
            out.append({"column": column.key, "op": condition["op"], "value": value})
        return out

    # --- actions --------------------------------------------------------------------------

    def _person(self, pk) -> int:
        try:
            pk = int(pk)
        except TypeError, ValueError:
            self.fail("actions", "Choose people in this company.")
        if pk not in self.ctx.people:
            self.fail("actions", "Choose people in this company.")
        return pk

    def _value(self, column, value):
        if column.type == "date" and isinstance(value, dict) and "today_plus" in value:
            try:
                return {"today_plus": max(-3650, min(int(value["today_plus"]), 3650))}
            except TypeError, ValueError:
                self.fail("actions", "Choose how many days from today.")
        if column.type == "people" and value in ("trigger_person", "creator"):
            return value
        try:
            return type_of(column).clean(value, column, self.ctx)
        except Invalid as error:
            self.fail("actions", f"{column.title}: {error}")

    def actions(self, raw) -> list:
        if not isinstance(raw, list) or not raw:
            self.fail("actions", "Add at least one action.")
        if len(raw) > MAX_ACTIONS:
            self.fail("actions", f"Add at most {MAX_ACTIONS} actions.")
        return [self.action(a) for a in raw]

    def action(self, raw) -> dict:
        if not isinstance(raw, dict) or raw.get("type") not in ACTIONS:
            self.fail("actions", "Choose what each action does.")
        kind = raw["type"]
        out = {"type": kind}
        if kind == "set_value":
            column = self.column("actions", raw.get("column"), writable=True)
            out |= {"column": column.key, "value": self._value(column, raw.get("value"))}
        elif kind == "clear_value":
            out["column"] = self.column("actions", raw.get("column"), writable=True).key
        elif kind == "copy_value":
            source = self.column("actions", raw.get("from"), allow_name=True)
            target = self.column("actions", raw.get("to"), writable=True, allow_name=True)
            if source is not None and target is not None and source.key == target.key:
                self.fail("actions", "Copy into a different column.")
            out |= {"from": raw["from"], "to": raw["to"]}
        elif kind == "increment":
            column = self.column("actions", raw.get("column"), ["number"])
            try:
                by = float(raw.get("by", 1))
            except TypeError, ValueError:
                self.fail("actions", "Choose how much to add.")
            out |= {"column": column.key, "by": str(by).rstrip("0").rstrip(".") or "0"}
        elif kind == "move_to_group":
            if raw.get("group") not in self.groups:
                self.fail("actions", "Choose one of this board's groups.")
            out["group"] = raw["group"]
        elif kind == "notify":
            people_column = raw.get("people_column") or None
            if people_column:
                people_column = self.column("actions", people_column, ["people"]).key
            members = [self._person(pk) for pk in (raw.get("members") or [])[:20]]
            trigger_person = bool(raw.get("trigger_person"))
            if not (people_column or members or trigger_person):
                self.fail("actions", "Choose who to notify.")
            message = str(raw.get("message") or "").strip()[:300]
            out |= {
                "people_column": people_column,
                "members": members,
                "trigger_person": trigger_person,
                "message": message,
            }
        elif kind == "create_item":
            target = (
                Board.objects.in_realm(self.board.realm_id)
                .select_related("project")
                .by_id(raw.get("board"))
            )
            if target is None or (
                self.membership is not None and not can(self.membership, target.project, "edit")
            ):
                self.fail("actions", "Choose a board you can edit.")
            groups = set(
                Group.objects.in_realm(target.realm_id)
                .of_board(target)
                .values_list("id", flat=True)
            )
            group = raw.get("group")
            if group is not None and group not in groups:
                self.fail("actions", "Choose one of that board's groups.")
            target_ctx = BoardContext(target)
            copies = []
            for pair in (raw.get("copy") or [])[:20]:
                if not isinstance(pair, dict):
                    continue
                self.column("actions", pair.get("from"), allow_name=True)
                to = target_ctx.by_key.get(pair.get("to"))
                if to is None or TYPES[to.type].computed:
                    self.fail("actions", "Copy into a column of the other board.")
                copies.append({"from": pair["from"], "to": pair["to"]})
            link = raw.get("link_column") or None
            if link:
                column = self.column("actions", link, ["connect"])
                if column.settings.get("board") != target.pk:
                    self.fail("actions", "That connect column links another board.")
                link = column.key
            out |= {
                "board": target.pk,
                "group": group,
                "name": str(raw.get("name") or "{name}").strip()[:255] or "{name}",
                "copy": copies,
                "link_column": link,
            }
        return out

    def delay(self, raw):
        if raw in (None, "", {}):
            return None
        if not isinstance(raw, dict) or raw.get("unit") not in DELAY_UNITS:
            self.fail("delay", "Choose minutes, hours or days.")
        try:
            amount = int(raw.get("amount"))
        except TypeError, ValueError:
            self.fail("delay", "Choose how long to wait.")
        if not 1 <= amount <= 365:
            self.fail("delay", "Wait from 1 to 365.")
        return {"amount": amount, "unit": raw["unit"]}


def delay_of(delay: dict | None) -> timedelta:
    if not delay:
        return timedelta(0)
    return DELAY_UNITS[delay["unit"]] * delay["amount"]
