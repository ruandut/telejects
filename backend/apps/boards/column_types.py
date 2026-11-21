"""Column types: how each kind of column checks, stores, shows, compares and charts a value
(0007). One registry, like the connector definitions: a new type is a class here, and the board,
automations and analytics all follow it.

Values are stored per item as JSON, keyed by the column's `key`:
- text, long_text, email, phone: a string
- number: a string holding an exact decimal ("1250.5")
- status: a label id from the column's settings; dropdown: a list of option ids
- date: "YYYY-MM-DD"; timeline: {"start": date, "end": date}
- people: a list of membership ids; connect: a list of item ids on the connected board
- checkbox: true; rating: 1..max
- link: {"url", "text"}; location: {"lat", "lng", "address"}
Formula, mirror, item id, created and last updated are computed when read, never stored.
A blank value is never stored: setting one removes the key.
"""

import datetime as dt
import re
import secrets
from decimal import Decimal, InvalidOperation

from django.utils import timezone

COLOURS = [
    "grey",
    "green",
    "amber",
    "red",
    "blue",
    "purple",
    "pink",
    "teal",
    "orange",
    "lime",
    "indigo",
    "brown",
]


class Invalid(ValueError):
    """A value the column can't hold. The message is shown to the person."""


def new_id() -> str:
    return secrets.token_hex(3)


def _blank(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _decimal(value) -> Decimal | None:
    if _blank(value) or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(" ", "").replace(",", ""))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text == "today":
        return timezone.localdate()
    for parse in (
        lambda t: dt.date.fromisoformat(t[:10]),
        lambda t: dt.datetime.strptime(t, "%d/%m/%Y").date(),
        lambda t: dt.datetime.strptime(t, "%Y/%m/%d").date(),
        # As monday.com and spreadsheets write them: "Nov 20, 2026", "20 Nov 2026".
        lambda t: dt.datetime.strptime(t, "%b %d, %Y").date(),
        lambda t: dt.datetime.strptime(t, "%B %d, %Y").date(),
        lambda t: dt.datetime.strptime(t, "%d %b %Y").date(),
        lambda t: dt.datetime.strptime(t, "%d %B %Y").date(),
    ):
        try:
            return parse(text)
        except ValueError:
            continue
    return None


class ColumnType:
    key = ""
    label = ""
    computed = False  # never stored: worked out when read
    numeric = False  # can be summed and averaged in charts
    chartable = True  # can group a chart

    def default_settings(self) -> dict:
        return {}

    def clean_settings(self, settings: dict, column=None) -> dict:
        return {}

    def clean(self, value, column, ctx):
        """The value to store, or None to clear it. Raises Invalid."""
        raise NotImplementedError

    def text(self, value, column, ctx) -> str:
        """How it reads in a sentence (notifications, imports, formulas, CSV)."""
        return "" if _blank(value) else str(value)

    def formula_value(self, value, column, ctx):
        return self.text(value, column, ctx) or None

    def number(self, value, column) -> Decimal | None:
        return None

    def groups(self, value, column, ctx) -> list[tuple[str, str]]:
        """(key, label) pairs this value falls under in a chart; [] when blank."""
        t = self.text(value, column, ctx)
        return [(t.lower(), t)] if t else []

    def sort_key(self, value, column, ctx):
        return self.text(value, column, ctx).lower()

    def matches(self, value, op: str, operand, column, ctx) -> bool:
        """Conditions in automations, filters in views and charts."""
        if op == "is_empty":
            return _blank(value)
        if op == "is_not_empty":
            return not _blank(value)
        text = self.text(value, column, ctx).lower()
        wanted = [str(o).lower() for o in (operand if isinstance(operand, list) else [operand])]
        if op == "is":
            return text in wanted or any(self._is(value, o, column, ctx) for o in wanted)
        if op == "is_not":
            return not self.matches(value, "is", operand, column, ctx)
        if op == "contains":
            return any(w and w in text for w in wanted)
        number = self.number(value, column)
        if op in ("gt", "lt", "gte", "lte"):
            limit = _decimal(operand)
            if number is None or limit is None:
                date, bound = _date(value), _date(operand)
                if date is None or bound is None:
                    return False
                number, limit = Decimal(date.toordinal()), Decimal(bound.toordinal())
            return {
                "gt": number > limit,
                "lt": number < limit,
                "gte": number >= limit,
                "lte": number <= limit,
            }[op]
        return False

    def _is(self, value, operand, column, ctx) -> bool:
        return False


class Text(ColumnType):
    key, label, limit = "text", "Text", 2000

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            raise Invalid("Enter some text.")
        text = str(value).strip()
        if len(text) > self.limit:
            raise Invalid(f"Keep it to {self.limit} characters.")
        return text or None


class LongText(Text):
    key, label, limit = "long_text", "Long text", 20000
    chartable = False


class Email(Text):
    key, label, limit = "email", "Email", 254
    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def clean(self, value, column, ctx):
        text = super().clean(value, column, ctx)
        if text and not self.pattern.match(text):
            raise Invalid("Enter an email address.")
        return text.lower() if text else None


class Phone(Text):
    key, label, limit = "phone", "Phone", 40

    def clean(self, value, column, ctx):
        text = super().clean(value, column, ctx)
        if text and not re.fullmatch(r"[+\d][\d\s()\-]{3,38}", text):
            raise Invalid("Enter a phone number.")
        return text


class Number(ColumnType):
    key, label, numeric = "number", "Numbers", True

    def default_settings(self):
        return {"unit": "", "unit_position": "left", "decimals": None}

    def clean_settings(self, settings, column=None):
        unit = str(settings.get("unit") or "")[:8]
        position = (
            settings.get("unit_position") if settings.get("unit_position") == "right" else "left"
        )
        decimals = settings.get("decimals")
        if decimals is not None:
            try:
                decimals = max(0, min(int(decimals), 6))
            except TypeError, ValueError:
                decimals = None
        return {"unit": unit, "unit_position": position, "decimals": decimals}

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        number = _decimal(value)
        if number is None:
            raise Invalid("Enter a number.")
        if abs(number) >= Decimal("1e15"):
            raise Invalid("That number is too large.")
        number = number.quantize(Decimal("0.000001")).normalize()
        return format(number, "f")

    def number(self, value, column):
        return _decimal(value)

    def text(self, value, column, ctx):
        n = _decimal(value)
        if n is None:
            return ""
        s = column.settings if column else {}
        decimals = s.get("decimals")
        shown = f"{n:,.{decimals}f}" if decimals is not None else f"{n:,f}".rstrip("0").rstrip(".")
        unit = s.get("unit") or ""
        if not unit:
            return shown
        return f"{shown} {unit}" if s.get("unit_position") == "right" else f"{unit}{shown}"

    def formula_value(self, value, column, ctx):
        return _decimal(value)

    def groups(self, value, column, ctx):
        n = _decimal(value)
        return [] if n is None else [(format(n.normalize(), "f"), self.text(value, column, ctx))]

    def sort_key(self, value, column, ctx):
        n = _decimal(value)
        return (n is None, n or 0)

    def _is(self, value, operand, column, ctx):
        a, b = _decimal(value), _decimal(operand)
        return a is not None and a == b


class Labels(ColumnType):
    """Shared by status (one label) and dropdown (many)."""

    setting = "labels"

    def clean_settings(self, settings, column=None):
        labels, seen = [], set()
        for raw in (settings.get(self.setting) or [])[:60]:
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()[:60]
            if not label or label.lower() in seen:
                continue
            seen.add(label.lower())
            colour = raw.get("colour") if raw.get("colour") in COLOURS else "grey"
            label_id = str(raw.get("id") or new_id())[:12]
            labels.append(
                {"id": label_id, "label": label, "colour": colour, "done": bool(raw.get("done"))}
            )
        if not labels and self.key == "status":
            raise Invalid("A status column needs at least one label.")
        return {**settings, self.setting: labels}

    def _labels(self, column):
        return (column.settings or {}).get(self.setting, []) if column else []

    def find(self, column, wanted):
        if _blank(wanted):
            return None
        wanted = str(wanted).strip()
        for label in self._labels(column):
            if label["id"] == wanted or label["label"].lower() == wanted.lower():
                return label
        return None

    def label_of(self, column, label_id) -> str:
        found = self.find(column, label_id)
        return found["label"] if found else ""


class Status(Labels):
    key, label = "status", "Status"

    def default_settings(self):
        return {
            "labels": [
                {"id": "todo", "label": "Not started", "colour": "grey", "done": False},
                {"id": "doing", "label": "Working on it", "colour": "amber", "done": False},
                {"id": "stuck", "label": "Stuck", "colour": "red", "done": False},
                {"id": "done", "label": "Done", "colour": "green", "done": True},
            ]
        }

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        found = self.find(column, value)
        if found is None:
            raise Invalid(f"Choose one of this column's labels, not {str(value)[:40]!r}.")
        return found["id"]

    def text(self, value, column, ctx):
        return self.label_of(column, value)

    def groups(self, value, column, ctx):
        found = self.find(column, value)
        return [(found["label"].lower(), found["label"])] if found else []

    def sort_key(self, value, column, ctx):
        ids = [label["id"] for label in self._labels(column)]
        return ids.index(value) if value in ids else len(ids)

    def _is(self, value, operand, column, ctx):
        found = self.find(column, operand)
        return found is not None and found["id"] == value

    def is_done(self, value, column) -> bool:
        found = self.find(column, value)
        return bool(found and found["done"])


class Dropdown(Labels):
    key, label, setting = "dropdown", "Dropdown", "options"

    def default_settings(self):
        return {"options": []}

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        wanted = value if isinstance(value, list) else [v for v in str(value).split(",")]
        chosen = []
        for want in wanted[:30]:
            if _blank(want):
                continue
            found = self.find(column, want)
            if found is None:
                raise Invalid(f"{str(want)[:40]!r} isn't one of this column's options.")
            if found["id"] not in chosen:
                chosen.append(found["id"])
        return chosen or None

    def text(self, value, column, ctx):
        return ", ".join(
            self.label_of(column, v) for v in (value or []) if self.label_of(column, v)
        )

    def groups(self, value, column, ctx):
        return [
            (self.label_of(column, v).lower(), self.label_of(column, v))
            for v in value or []
            if self.label_of(column, v)
        ]

    def _is(self, value, operand, column, ctx):
        found = self.find(column, operand)
        return found is not None and found["id"] in (value or [])


class Date(ColumnType):
    key, label = "date", "Date"

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        date = _date(value)
        if date is None:
            raise Invalid("Enter a date.")
        return date.isoformat()

    def text(self, value, column, ctx):
        date = _date(value)
        return date.isoformat() if date else ""

    def formula_value(self, value, column, ctx):
        return _date(value)

    def sort_key(self, value, column, ctx):
        date = _date(value)
        return (date is None, date or dt.date.min)

    def day(self, value) -> dt.date | None:
        return _date(value)


class Timeline(ColumnType):
    key, label = "timeline", "Timeline"

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        if not isinstance(value, dict):
            raise Invalid("Choose a start and an end.")
        start, end = _date(value.get("start")), _date(value.get("end"))
        if start is None or end is None:
            raise Invalid("Choose a start and an end.")
        if end < start:
            raise Invalid("The end can't be before the start.")
        return {"start": start.isoformat(), "end": end.isoformat()}

    def text(self, value, column, ctx):
        if not isinstance(value, dict):
            return ""
        return f"{value.get('start')} – {value.get('end')}"

    def formula_value(self, value, column, ctx):
        return _date(value.get("end")) if isinstance(value, dict) else None

    def sort_key(self, value, column, ctx):
        date = _date(value.get("start")) if isinstance(value, dict) else None
        return (date is None, date or dt.date.min)

    def day(self, value, part="end") -> dt.date | None:
        return _date(value.get(part)) if isinstance(value, dict) else None


class People(ColumnType):
    key, label = "people", "People"

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        wanted = value if isinstance(value, list) else [value]
        ids = []
        for want in wanted[:30]:
            try:
                ids.append(int(want))
            except TypeError, ValueError:
                person = ctx.person_named(str(want))
                if person is None:
                    raise Invalid(f"{str(want)[:40]!r} isn't anyone in this company.") from None
                ids.append(person)
        unknown = [i for i in ids if i not in ctx.people]
        if unknown:
            raise Invalid("Choose people in this company.")
        return list(dict.fromkeys(ids)) or None

    def text(self, value, column, ctx):
        return ", ".join(ctx.people.get(i, "Someone") for i in value or [])

    def groups(self, value, column, ctx):
        return [(str(i), ctx.people.get(i, "Someone")) for i in value or []]

    def _is(self, value, operand, column, ctx):
        try:
            return int(operand) in (value or [])
        except TypeError, ValueError:
            return False


class Checkbox(ColumnType):
    key, label = "checkbox", "Checkbox"

    def clean(self, value, column, ctx):
        if isinstance(value, str):
            value = value.strip().lower() in ("true", "yes", "y", "1", "x", "done", "✓")
        return True if value else None

    def text(self, value, column, ctx):
        return "Yes" if value else "No"

    def formula_value(self, value, column, ctx):
        return bool(value)

    def groups(self, value, column, ctx):
        return [("yes", "Checked")] if value else [("no", "Unchecked")]

    def matches(self, value, op, operand, column, ctx):
        if op in ("is_empty", "is_not_empty"):
            return super().matches(value, op, operand, column, ctx)
        if op in ("is", "is_not"):
            want = str(operand).lower() in ("true", "yes", "1", "checked")
            return (bool(value) == want) == (op == "is")
        return False


class Rating(ColumnType):
    key, label, numeric = "rating", "Rating", True

    def default_settings(self):
        return {"max": 5}

    def clean_settings(self, settings, column=None):
        try:
            top = max(1, min(int(settings.get("max") or 5), 10))
        except TypeError, ValueError:
            top = 5
        return {"max": top}

    def clean(self, value, column, ctx):
        if _blank(value) or value == 0:
            return None
        try:
            n = int(value)
        except TypeError, ValueError:
            raise Invalid("Choose a rating.") from None
        top = (column.settings or {}).get("max", 5)
        if not 1 <= n <= top:
            raise Invalid(f"Choose 1 to {top}.")
        return n

    def number(self, value, column):
        return _decimal(value)

    def formula_value(self, value, column, ctx):
        return _decimal(value)

    def text(self, value, column, ctx):
        return "" if not value else f"{value}/{(column.settings or {}).get('max', 5)}"


class Link(ColumnType):
    key, label, chartable = "link", "Link", False

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        if isinstance(value, str):
            value = {"url": value}
        if not isinstance(value, dict):
            raise Invalid("Enter a web address.")
        url = str(value.get("url") or "").strip()
        if url and "://" not in url:
            url = "https://" + url
        if not re.fullmatch(r"https?://[^\s<>\"']{3,2000}", url):
            raise Invalid("Enter a web address starting with http:// or https://.")
        return {"url": url, "text": str(value.get("text") or "").strip()[:200]}

    def text(self, value, column, ctx):
        return (value.get("text") or value.get("url") or "") if isinstance(value, dict) else ""


class Location(ColumnType):
    key, label, chartable = "location", "Location", False

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",")]
            if len(parts) == 2 and all(_decimal(p) is not None for p in parts):
                value = {"lat": parts[0], "lng": parts[1]}
            else:
                value = {"address": value}
        if not isinstance(value, dict):
            raise Invalid("Enter coordinates or an address.")
        lat, lng = _decimal(value.get("lat")), _decimal(value.get("lng"))
        address = str(value.get("address") or "").strip()[:300]
        if (lat is None) != (lng is None):
            raise Invalid("Enter both the latitude and the longitude.")
        if lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise Invalid("Those coordinates aren't on the map.")
        if lat is None and not address:
            return None
        out = {"address": address}
        if lat is not None:
            out |= {"lat": float(round(lat, 7)), "lng": float(round(lng, 7))}
        return out

    def text(self, value, column, ctx):
        if not isinstance(value, dict):
            return ""
        if value.get("address"):
            return value["address"]
        if value.get("lat") is not None:
            return f"{value['lat']}, {value['lng']}"
        return ""


class Connect(ColumnType):
    """Links items on another board (settings: board). Shows only items the viewer can see."""

    key, label, chartable = "connect", "Connect boards", False

    def clean_settings(self, settings, column=None):
        return {"board": settings.get("board")}

    def clean(self, value, column, ctx):
        if _blank(value):
            return None
        wanted = value if isinstance(value, list) else [value]
        try:
            ids = list(dict.fromkeys(int(v) for v in wanted[:50]))
        except TypeError, ValueError:
            raise Invalid("Choose items on the connected board.") from None
        board_id = (column.settings or {}).get("board")
        found = ctx.items_on_board(board_id, ids)
        if set(ids) - found:
            raise Invalid("Choose items on the connected board.")
        return ids or None

    def text(self, value, column, ctx):
        return ", ".join(ctx.item_names(value or []))


class Computed(ColumnType):
    computed = True

    def clean(self, value, column, ctx):
        raise Invalid("This column is worked out by itself.")


class Formula(Computed):
    key, label = "formula", "Formula"

    def default_settings(self):
        return {"expression": ""}

    def clean_settings(self, settings, column=None):
        from .formula import compile_formula

        expression = str(settings.get("expression") or "")
        compile_formula(expression)  # raises FormulaError, a ValueError
        return {"expression": expression, "unit": str(settings.get("unit") or "")[:8]}

    def number(self, value, column):
        return _decimal(value)

    numeric = True

    def text(self, value, column, ctx):
        if _blank(value):
            return ""
        unit = (column.settings or {}).get("unit") if column else ""
        return f"{unit}{value}" if unit and _decimal(value) is not None else str(value)

    def formula_value(self, value, column, ctx):
        n = _decimal(value)
        return n if n is not None and not isinstance(value, bool) else value


class Mirror(Computed):
    """Shows a column of the items a connect column links to (settings: connect_column, the
    connect column's key; target_column, the other board's column key)."""

    key, label = "mirror", "Mirror"

    def clean_settings(self, settings, column=None):
        return {
            "connect_column": str(settings.get("connect_column") or ""),
            "target_column": str(settings.get("target_column") or ""),
        }

    def text(self, value, column, ctx):
        if not isinstance(value, dict):
            return ""
        shown = [v["text"] for v in value.get("items", []) if v.get("text")]
        if value.get("hidden"):
            shown.append(f"{value['hidden']} hidden")
        return ", ".join(shown)

    def groups(self, value, column, ctx):
        if not isinstance(value, dict):
            return []
        return [(v["text"].lower(), v["text"]) for v in value.get("items", []) if v.get("text")]

    def number(self, value, column):
        if not isinstance(value, dict):
            return None
        nums = [_decimal(v.get("number")) for v in value.get("items", [])]
        nums = [n for n in nums if n is not None]
        return sum(nums, Decimal(0)) if nums else None


class ItemId(Computed):
    key, label, chartable = "item_id", "Item ID", False

    def text(self, value, column, ctx):
        return "" if value is None else str(value)


class Created(Computed):
    key, label = "created", "Creation log"

    def text(self, value, column, ctx):
        return (value or {}).get("at", "")[:10] if isinstance(value, dict) else ""


class Updated(Computed):
    key, label = "updated", "Last updated"

    def text(self, value, column, ctx):
        return (value or {}).get("at", "")[:10] if isinstance(value, dict) else ""


TYPES: dict[str, ColumnType] = {
    t.key: t
    for t in (
        Status(),
        Text(),
        LongText(),
        Number(),
        Date(),
        Timeline(),
        People(),
        Dropdown(),
        Checkbox(),
        Rating(),
        Link(),
        Email(),
        Phone(),
        Location(),
        Connect(),
        Mirror(),
        Formula(),
        ItemId(),
        Created(),
        Updated(),
    )
}


def type_of(column) -> ColumnType:
    return TYPES[column.type]
