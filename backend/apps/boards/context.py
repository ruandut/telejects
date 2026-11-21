"""What reading or checking a board's values needs: its columns, the company's people, and the
computed columns (formula, mirror, item id, created, updated), worked out for one person.

`membership` decides what connect and mirror columns may show: only items on boards that
person may open. Without one (automations, which act for the whole board), every item in the
company counts.
"""

from functools import cached_property

from apps.realms.models import RealmMembership

from .column_types import TYPES, Status, type_of
from .formula import FormulaError, as_value, compile_formula, evaluate
from .models import Board, Column, Item

MAX_FORMULA_DEPTH = 5


class BoardContext:
    def __init__(self, board: Board, membership=None, columns=None):
        self.board = board
        self.membership = membership
        self.realm_id = board.realm_id
        if columns is None:
            columns = Column.objects.in_realm(board.realm_id).of_board(board)
        self.columns: list[Column] = list(columns)
        self.by_key = {c.key: c for c in self.columns}
        self._formulas: dict[str, tuple] = {}

    # --- people and items -------------------------------------------------------------------

    @cached_property
    def people(self) -> dict[int, str]:
        rows = (
            RealmMembership.objects.in_realm(self.realm_id)
            .current()
            .select_related("user")
            .order_by("id")
        )
        return {m.pk: m.display_name for m in rows}

    def person_named(self, name: str) -> int | None:
        name = name.strip().lower()
        for pk, shown in self.people.items():
            if shown.lower() == name:
                return pk
        rows = (
            RealmMembership.objects.in_realm(self.realm_id)
            .current()
            .filter(user__email__iexact=name)
        )
        found = rows.values_list("id", flat=True).first()
        return found

    def _items(self):
        items = Item.objects.in_realm(self.realm_id)
        return items.visible_to(self.membership) if self.membership is not None else items

    def items_on_board(self, board_id, ids) -> set[int]:
        if not board_id or not ids:
            return set()
        return set(
            self._items().live().filter(board_id=board_id, id__in=ids).values_list("id", flat=True)
        )

    def item_names(self, ids) -> list[str]:
        return list(self._items().filter(id__in=ids).values_list("name", flat=True))

    # --- the board's own columns ------------------------------------------------------------

    @property
    def status_column(self) -> Column | None:
        chosen = self.by_key.get(self.board.status_column)
        if chosen is not None and chosen.type == "status":
            return chosen
        return next((c for c in self.columns if c.type == "status"), None)

    @property
    def due_column(self) -> Column | None:
        chosen = self.by_key.get(self.board.due_column)
        return chosen if chosen is not None and chosen.type in ("date", "timeline") else None

    def is_done(self, values: dict) -> bool:
        column = self.status_column
        if column is None:
            return False
        status: Status = TYPES["status"]
        return status.is_done(values.get(column.key), column)

    def text(self, column: Column, value) -> str:
        return type_of(column).text(value, column, self)

    # --- computed columns -------------------------------------------------------------------

    def _formula(self, column):
        if column.key not in self._formulas:
            try:
                tree, titles = compile_formula(column.settings.get("expression", ""))
            except FormulaError:
                tree, titles = None, []
            self._formulas[column.key] = (tree, titles)
        return self._formulas[column.key]

    def _column_titled(self, title: str) -> Column | None:
        title = title.strip().lower()
        if title in ("name", "item", "item name"):
            return None
        return next((c for c in self.columns if c.title.strip().lower() == title), None)

    def formula_value(self, column, item, values, depth=0):
        tree, titles = self._formula(column)
        if tree is None or depth > MAX_FORMULA_DEPTH:
            return None
        variables = []
        for title in titles:
            ref = self._column_titled(title)
            if ref is None:
                variables.append(
                    item.name if title.lower() in ("name", "item", "item name") else None
                )
            elif ref.type == "formula":
                variables.append(
                    type_of(ref).formula_value(
                        self.formula_value(ref, item, values, depth + 1), ref, self
                    )
                )
            elif ref.type == "item_id":
                variables.append(item.number)
            else:
                variables.append(type_of(ref).formula_value(values.get(ref.key), ref, self))
        return as_value(evaluate(tree, variables))

    def computed(self, items) -> dict[int, dict]:
        """{item id: {column key: value}} for every computed column, and connect columns as
        {"items": [...], "hidden": n} with only what this person may see."""
        out: dict[int, dict] = {item.pk: {} for item in items}
        connects = [c for c in self.columns if c.type == "connect"]
        mirrors = [c for c in self.columns if c.type == "mirror"]
        linked: dict[int, Item] = {}
        if connects:
            ids = {i for item in items for c in connects for i in (item.values.get(c.key) or [])}
            if ids:
                linked = {
                    i.pk: i for i in self._items().live().filter(id__in=ids).select_related("board")
                }
        targets: dict[tuple[int, str], Column] = {}
        if mirrors and linked:
            board_ids = {i.board_id for i in linked.values()}
            for col in Column.objects.in_realm(self.realm_id).filter(board_id__in=board_ids):
                targets[(col.board_id, col.key)] = col
        target_ctx = {}

        for item in items:
            values = item.values or {}
            row = out[item.pk]
            for column in self.columns:
                kind = column.type
                if kind == "item_id":
                    row[column.key] = item.number
                elif kind == "created":
                    row[column.key] = {
                        "at": item.created_at.isoformat() if item.created_at else None,
                        "by": self.people.get(item.created_by_id) if item.created_by_id else None,
                    }
                elif kind == "updated":
                    row[column.key] = {
                        "at": item.updated_at.isoformat() if item.updated_at else None
                    }
                elif kind == "formula":
                    row[column.key] = self.formula_value(column, item, values)
                elif kind == "connect":
                    ids = values.get(column.key) or []
                    shown = [linked[i] for i in ids if i in linked]
                    row[column.key] = {
                        "items": [{"id": i.pk, "name": i.name, "board": i.board_id} for i in shown],
                        "hidden": len(ids) - len(shown),
                    }
            for column in mirrors:
                connect = self.by_key.get(column.settings.get("connect_column", ""))
                target_key = column.settings.get("target_column", "")
                ids = (values.get(connect.key) or []) if connect else []
                shown = []
                for i in ids:
                    other = linked.get(i)
                    if other is None:
                        continue
                    if target_key == "name":
                        shown.append({"id": i, "text": other.name, "number": None})
                        continue
                    target = targets.get((other.board_id, target_key))
                    if target is None or target.type in ("formula", "mirror", "connect"):
                        continue
                    ctx = target_ctx.setdefault(other.board_id, self)
                    value = other.values.get(target_key)
                    number = type_of(target).number(value, target)
                    entry = {
                        "id": i,
                        "text": type_of(target).text(value, target, ctx),
                        "number": None if number is None else format(number, "f"),
                    }
                    if target.type == "status":
                        label = TYPES["status"].find(target, value)
                        entry["colour"] = label["colour"] if label else None
                    shown.append(entry)
                row[column.key] = {
                    "items": shown,
                    "hidden": len(ids) - len([i for i in ids if i in linked]),
                }
        return out

    def full_values(self, items) -> dict[int, dict]:
        """Stored and computed values together, as the API and charts read them."""
        computed = self.computed(items)
        return {item.pk: {**(item.values or {}), **computed[item.pk]} for item in items}
