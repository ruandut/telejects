"""Boards' writes and workflows (0007): the only place that changes boards, groups, columns,
items, updates and views. Every change to an item is recorded in its activity, published to the
board's live topic (ids only), and signalled for automations.

A cell is saved on its own (`set_values`), under a row lock and merged into the item's other
values, so two people editing different cells of one item keep both changes.
"""

import re
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F, Func, Max, Min, Value
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.notifications import services as notify
from apps.realms.events import publish
from apps.realms.models import RealmMembership

from . import signals
from .column_types import TYPES, Invalid, type_of
from .context import BoardContext
from .models import Board, BoardView, Column, Group, Item, ItemActivity, ItemUpdate
from .templates import TEMPLATES

MAX_IMPORT_ROWS = 5000


@dataclass(frozen=True)
class Actor:
    """Who makes a change: a person, or an automation (and how deep in a chain it is)."""

    membership: RealmMembership | None = None
    automation_id: int | None = None
    automation_name: str = ""
    depth: int = 0

    @property
    def membership_id(self):
        return self.membership.pk if self.membership is not None else None


SYSTEM = Actor()


def _changed(board: Board, items=None):
    """Tell the board's open tabs: these items changed (or, without items, the board itself)."""
    publish(board.realm_id, "board", board.pk, items)


def _activity(item, actor: Actor, kind, **fields):
    return ItemActivity(
        realm_id=item.realm_id,
        item=item,
        board_id=item.board_id,
        kind=kind,
        actor=actor.membership,
        automation_id=actor.automation_id,
        automation_name=actor.automation_name[:120],
        **fields,
    )


def _short(text: str) -> str:
    return text if len(text) <= 300 else text[:297] + "…"


# --- boards ----------------------------------------------------------------------------------


def _next_position(queryset) -> float:
    top = queryset.aggregate(top=Max("position"))["top"]
    return (top or 0) + 1


@transaction.atomic
def create_board(project, name: str = "", template: str = "blank", actor: Actor = SYSTEM):
    spec = TEMPLATES.get(template) or TEMPLATES["blank"]
    board = Board.objects.create(
        realm_id=project.realm_id,
        project=project,
        name=(name or spec["board"]).strip()[:120],
        position=_next_position(Board.objects.in_realm(project.realm_id).of_project(project)),
        status_column=spec["status_column"],
        due_column=spec["due_column"],
    )
    for i, (group, colour) in enumerate(spec["groups"]):
        Group.objects.create(
            realm_id=board.realm_id, board=board, name=group, colour=colour, position=i
        )
    for i, (key, title, kind, settings) in enumerate(spec["columns"]):
        column_type = TYPES[kind]
        Column.objects.create(
            realm_id=board.realm_id,
            board=board,
            key=key,
            title=title,
            type=kind,
            settings=column_type.clean_settings({**column_type.default_settings(), **settings}),
            position=i,
            width=_width(kind),
        )
    BoardView.objects.create(realm_id=board.realm_id, board=board, name="Main table", position=0)
    if spec["status_column"]:
        BoardView.objects.create(
            realm_id=board.realm_id,
            board=board,
            name="Kanban",
            kind=BoardView.Kind.KANBAN,
            config={"kanban_column": spec["status_column"]},
            position=1,
        )
    signals.board_created.send(sender=Board, board=board, template=template, actor=actor)
    return board


def _width(kind: str) -> int:
    return {"long_text": 220, "location": 200, "people": 140, "status": 150, "timeline": 200}.get(
        kind, 150
    )


@transaction.atomic
def update_board(board: Board, **fields) -> Board:
    allowed = {"name", "description", "status_column", "due_column", "position"}
    for name, value in fields.items():
        if name not in allowed:
            raise ValueError(name)
        setattr(board, name, value)
    if "status_column" in fields or "due_column" in fields:
        ctx = BoardContext(board)
        if board.status_column and (
            ctx.by_key.get(board.status_column) is None
            or ctx.by_key[board.status_column].type != "status"
        ):
            raise ValidationError({"status_column": "Choose a status column."})
        if board.due_column and (
            ctx.by_key.get(board.due_column) is None
            or ctx.by_key[board.due_column].type not in ("date", "timeline")
        ):
            raise ValidationError({"due_column": "Choose a date or timeline column."})
    board.save()
    if "status_column" in fields:
        recompute_done(board)
    _changed(board)
    return board


def delete_board(board: Board) -> None:
    realm_id, pk = board.realm_id, board.pk
    board.delete()
    publish(realm_id, "board", pk)


def recompute_done(board: Board) -> None:
    ctx = BoardContext(board)
    now = timezone.now()
    for item in Item.objects.in_realm(board.realm_id).of_board(board).select_for_update():
        done = ctx.is_done(item.values)
        if done != item.done:
            item.done = done
            item.completed_at = now if done else None
            item.save(update_fields=["done", "completed_at"])


# --- groups ----------------------------------------------------------------------------------


@transaction.atomic
def create_group(board: Board, name: str, colour: str = "blue", top: bool = False) -> Group:
    groups = Group.objects.in_realm(board.realm_id).of_board(board)
    if top:
        position = (groups.aggregate(low=Min("position"))["low"] or 0) - 1
    else:
        position = _next_position(groups)
    group = Group.objects.create(
        realm_id=board.realm_id,
        board=board,
        name=name.strip()[:120] or "New group",
        colour=colour,
        position=position,
    )
    _changed(board)
    return group


@transaction.atomic
def update_group(group: Group, **fields) -> Group:
    for name in ("name", "colour", "position"):
        if name in fields:
            setattr(group, name, fields[name])
    group.save()
    _changed(group.board)
    return group


@transaction.atomic
def delete_group(group: Group) -> None:
    groups = Group.objects.in_realm(group.realm_id).of_board(group.board)
    if groups.count() <= 1:
        raise ValidationError({"detail": "A board keeps at least one group."})
    board = group.board
    group.delete()
    _changed(board)


# --- columns ---------------------------------------------------------------------------------


def _clean_settings(kind: str, settings, board: Board, column=None) -> dict:
    column_type = TYPES[kind]
    try:
        cleaned = column_type.clean_settings(
            {**column_type.default_settings(), **(settings or {})}, column
        )
    except ValueError as error:
        raise ValidationError({"settings": str(error)}) from error
    if kind == "connect":
        target = (
            Board.objects.in_realm(board.realm_id).by_id(cleaned.get("board"))
            if cleaned.get("board")
            else None
        )
        if target is None:
            raise ValidationError({"settings": "Choose the board to connect."})
        cleaned["board"] = target.pk
    if kind == "mirror":
        ctx = BoardContext(board)
        connect = ctx.by_key.get(cleaned["connect_column"])
        if connect is None or connect.type != "connect":
            raise ValidationError({"settings": "Choose a connect column to mirror through."})
        target_board = connect.settings.get("board")
        if cleaned["target_column"] != "name" and not (
            Column.objects.in_realm(board.realm_id)
            .filter(board_id=target_board, key=cleaned["target_column"])
            .exists()
        ):
            raise ValidationError({"settings": "Choose a column of the connected board."})
    return cleaned


def _new_key(board: Board, kind: str) -> str:
    taken = set(
        Column.objects.in_realm(board.realm_id).of_board(board).values_list("key", flat=True)
    )
    base = re.sub(r"[^a-z]", "", kind)[:12] or "col"
    n = 1
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


@transaction.atomic
def create_column(board, title: str, kind: str, settings=None, description="", after=None):
    if kind not in TYPES:
        raise ValidationError({"type": "Choose a column type."})
    columns = Column.objects.in_realm(board.realm_id).of_board(board)
    if columns.count() >= 80:
        raise ValidationError({"detail": "A board can have at most 80 columns."})
    position = _next_position(columns)
    if after is not None:
        anchor = columns.filter(key=after).first()
        if anchor is not None:
            nxt = columns.filter(position__gt=anchor.position).aggregate(n=Min("position"))["n"]
            position = (anchor.position + nxt) / 2 if nxt is not None else anchor.position + 1
    column = Column.objects.create(
        realm_id=board.realm_id,
        board=board,
        key=_new_key(board, kind),
        title=(title or TYPES[kind].label).strip()[:80],
        type=kind,
        settings=_clean_settings(kind, settings, board),
        description=description[:300],
        position=position,
        width=_width(kind),
    )
    _changed(board)
    return column


@transaction.atomic
def update_column(column: Column, **fields) -> Column:
    board = column.board
    was_done = column.settings if column.type == "status" else None
    if "settings" in fields:
        column.settings = _clean_settings(column.type, fields.pop("settings"), board, column)
    for name in ("title", "description", "width", "position"):
        if name in fields:
            setattr(column, name, fields[name])
    column.title = column.title.strip()[:80] or TYPES[column.type].label
    column.save()
    if was_done is not None and was_done != column.settings:
        recompute_done(board)
    _changed(board)
    return column


@transaction.atomic
def delete_column(column: Column) -> None:
    board = column.board
    key = column.key
    Item.objects.in_realm(board.realm_id).of_board(board).filter(values__has_key=key).update(
        values=Func(F("values"), Value(key), function="", arg_joiner=" - ")
    )
    column.delete()
    changed = []
    if board.status_column == key:
        board.status_column = ""
        changed.append("status_column")
    if board.due_column == key:
        board.due_column = ""
        changed.append("due_column")
    if changed:
        board.save(update_fields=changed)
        recompute_done(board)
    _changed(board)


# --- items -----------------------------------------------------------------------------------


def _clean_values(ctx: BoardContext, raw: dict) -> dict:
    """{key: cleaned or None}. Raises ValidationError naming each column that refused."""
    if not isinstance(raw, dict):
        raise ValidationError({"values": "Send the values by column."})
    cleaned, problems = {}, {}
    for key, value in raw.items():
        column = ctx.by_key.get(key)
        if column is None:
            problems[key] = "There is no such column on this board."
            continue
        try:
            cleaned[key] = type_of(column).clean(value, column, ctx)
        except Invalid as error:
            problems[key] = str(error)
    if problems:
        raise ValidationError({"values": problems})
    return cleaned


def _clean_name(name) -> str:
    name = str(name or "").strip()[:255]
    if not name:
        raise ValidationError({"name": "Give the item a name."})
    return name


def _group_of(board: Board, group_id) -> Group:
    groups = Group.objects.in_realm(board.realm_id).of_board(board)
    group = groups.by_id(group_id) if group_id else groups.first()
    if group is None:
        raise ValidationError({"group": "Choose one of this board's groups."})
    return group


@transaction.atomic
def create_item(board, name, group=None, values=None, actor: Actor = SYSTEM, top=False, ctx=None):
    board = Board.objects.in_realm(board.realm_id).select_for_update().get(pk=board.pk)
    ctx = ctx or BoardContext(board, actor.membership)
    group = _group_of(board, group.pk if isinstance(group, Group) else group)
    cleaned = {k: v for k, v in _clean_values(ctx, values or {}).items() if v is not None}
    items = Item.objects.in_realm(board.realm_id).filter(group=group)
    if top:
        position = (items.aggregate(low=Min("position"))["low"] or 0) - 1
    else:
        position = _next_position(items)
    board.item_seq += 1
    board.save(update_fields=["item_seq"])
    done = ctx.is_done(cleaned)
    item = Item.objects.create(
        realm_id=board.realm_id,
        board=board,
        group=group,
        number=board.item_seq,
        name=_clean_name(name),
        position=position,
        values=cleaned,
        done=done,
        completed_at=timezone.now() if done else None,
        created_by=actor.membership,
    )
    _activity(item, actor, ItemActivity.Kind.CREATED, new_text=_short(item.name)).save()
    _changed(board, [item.pk])
    signals.item_created.send(sender=Item, item=item, actor=actor)
    return item


def _locked(item: Item) -> Item:
    return (
        Item.objects.in_realm(item.realm_id)
        .select_for_update()
        .select_related("board")
        .get(pk=item.pk)
    )


@transaction.atomic
def set_values(item: Item, raw: dict, actor: Actor = SYSTEM) -> Item:
    """Change some cells of one item. Only the cells sent change; returns the fresh item."""
    item = _locked(item)
    ctx = BoardContext(item.board, actor.membership)
    computed = [k for k in raw if k in ctx.by_key and ctx.by_key[k].type in _COMPUTED]
    if computed:
        raise ValidationError(
            {"values": {k: "This column is worked out by itself." for k in computed}}
        )
    cleaned = _clean_values(ctx, raw)
    changes = {}
    values = dict(item.values)
    for key, new in cleaned.items():
        old = values.get(key)
        if old == new:
            continue
        if new is None:
            values.pop(key, None)
        else:
            values[key] = new
        changes[key] = (old, new)
    if not changes:
        return item
    item.values = values
    done = ctx.is_done(values)
    if done != item.done:
        item.done = done
        item.completed_at = timezone.now() if done else None
    item.save()
    ItemActivity.objects.bulk_create(
        [
            _activity(
                item,
                actor,
                ItemActivity.Kind.VALUE,
                column_key=key,
                column_title=ctx.by_key[key].title,
                old=old,
                new=new,
                old_text=_short(ctx.text(ctx.by_key[key], old)),
                new_text=_short(ctx.text(ctx.by_key[key], new)),
            )
            for key, (old, new) in changes.items()
        ]
    )
    _notify_assigned(item, ctx, changes, actor)
    _changed(item.board, [item.pk])
    signals.values_changed.send(sender=Item, item=item, changes=changes, actor=actor)
    return item


_COMPUTED = {k for k, t in TYPES.items() if t.computed}


def _notify_assigned(item, ctx, changes, actor: Actor):
    """Someone newly put in a people column hears about it (not when they did it themselves)."""
    for key, (old, new) in changes.items():
        if ctx.by_key[key].type != "people":
            continue
        added = set(new or []) - set(old or [])
        added.discard(actor.membership_id)
        if added:
            notify.send(
                item.realm_id,
                sorted(added),
                kind="assigned",
                title=f"You were added to {item.name}",
                body=f"{ctx.by_key[key].title} on {item.board.name}",
                link=_link(item),
                actor=_actor_name(actor),
                allowed=lambda m, item=item: _may_see(m, item),
            )


def _link(item) -> dict:
    return {"project": item.board.project_id, "board": item.board_id, "item": item.pk}


def _actor_name(actor: Actor) -> str:
    if actor.automation_id:
        return f"Automation: {actor.automation_name}"
    return actor.membership.display_name if actor.membership is not None else "Telejects"


def _may_see(membership, item) -> bool:
    from apps.projects.access import can

    return can(membership, item.board.project, "view")


@transaction.atomic
def rename_item(item: Item, name: str, actor: Actor = SYSTEM) -> Item:
    item = _locked(item)
    name = _clean_name(name)
    if name == item.name:
        return item
    old = item.name
    item.name = name
    item.save(update_fields=["name", "updated_at"])
    _activity(
        item, actor, ItemActivity.Kind.NAME, old_text=_short(old), new_text=_short(name)
    ).save()
    _changed(item.board, [item.pk])
    return item


@transaction.atomic
def move_item(item: Item, group=None, before=None, after=None, actor: Actor = SYSTEM) -> Item:
    """Into another group and/or between two items (ids), or to the group's end."""
    item = _locked(item)
    board = item.board
    old_group = item.group
    target = _group_of(board, group) if group is not None else old_group
    siblings = Item.objects.in_realm(board.realm_id).filter(group=target).exclude(pk=item.pk)
    low = siblings.by_id(after).position if after and siblings.by_id(after) else None
    high = siblings.by_id(before).position if before and siblings.by_id(before) else None
    if low is not None and high is not None:
        position = (low + high) / 2
    elif high is not None:
        below = siblings.filter(position__lt=high).aggregate(p=Max("position"))["p"]
        position = (below + high) / 2 if below is not None else high - 1
    elif low is not None:
        above = siblings.filter(position__gt=low).aggregate(p=Min("position"))["p"]
        position = (low + above) / 2 if above is not None else low + 1
    else:
        position = _next_position(siblings) if target.pk != old_group.pk else item.position
    item.group = target
    item.position = position
    item.save(update_fields=["group", "position", "updated_at"])
    if target.pk != old_group.pk:
        _activity(
            item, actor, ItemActivity.Kind.MOVED, old_text=old_group.name, new_text=target.name
        ).save()
        signals.item_moved.send(sender=Item, item=item, from_group=old_group.pk, actor=actor)
    _changed(board, [item.pk])
    return item


@transaction.atomic
def archive_item(item: Item, actor: Actor = SYSTEM) -> Item:
    item = _locked(item)
    if item.archived_at is None:
        item.archived_at = timezone.now()
        item.save(update_fields=["archived_at", "updated_at"])
        _activity(item, actor, ItemActivity.Kind.ARCHIVED).save()
        _changed(item.board, [item.pk])
    return item


@transaction.atomic
def restore_item(item: Item, actor: Actor = SYSTEM) -> Item:
    item = _locked(item)
    if item.archived_at is not None:
        item.archived_at = None
        item.save(update_fields=["archived_at", "updated_at"])
        _activity(item, actor, ItemActivity.Kind.RESTORED).save()
        _changed(item.board, [item.pk])
    return item


@transaction.atomic
def delete_item(item: Item) -> None:
    board, pk = item.board, item.pk
    item.delete()
    _changed(board, [pk])


@transaction.atomic
def duplicate_item(item: Item, actor: Actor = SYSTEM) -> Item:
    return create_item(
        item.board,
        f"{item.name} (copy)"[:255],
        group=item.group_id,
        values=_restorable(item),
        actor=actor,
    )


def _restorable(item: Item) -> dict:
    ctx = BoardContext(item.board)
    return {k: v for k, v in item.values.items() if k in ctx.by_key}


@transaction.atomic
def batch(board: Board, ids, action: str, actor: Actor, payload: dict) -> int:
    items = list(Item.objects.in_realm(board.realm_id).of_board(board).filter(id__in=ids[:500]))
    for item in items:
        if action == "archive":
            archive_item(item, actor)
        elif action == "restore":
            restore_item(item, actor)
        elif action == "delete":
            delete_item(item)
        elif action == "move":
            move_item(item, group=payload.get("group"), actor=actor)
        elif action == "set":
            set_values(item, payload.get("values") or {}, actor)
        elif action == "duplicate":
            duplicate_item(item, actor)
        else:
            raise ValidationError(
                {"action": "Choose archive, restore, delete, move, set or duplicate."}
            )
    return len(items)


def import_rows(board: Board, rows, actor: Actor) -> dict:
    """Items from a file's rows: [{"name", "group"?, "values": {key: raw}}]. Each row is checked
    like an edit; rows that fail are reported by number and skipped."""
    if not isinstance(rows, list) or not rows:
        raise ValidationError({"rows": "Send at least one row."})
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValidationError({"rows": f"Import at most {MAX_IMPORT_ROWS:,} rows at a time."})
    ctx = BoardContext(board, actor.membership)
    created, errors = [], []
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append({"row": number, "errors": {"row": "Not a row."}})
            continue
        try:
            with transaction.atomic():
                item = create_item(
                    board,
                    row.get("name"),
                    group=row.get("group"),
                    values=row.get("values") or {},
                    actor=actor,
                    ctx=ctx,
                )
            created.append(item.pk)
        except ValidationError as error:
            errors.append({"row": number, "errors": error.detail})
    return {"created": len(created), "errors": errors[:200], "failed": len(errors)}


# --- updates ---------------------------------------------------------------------------------


@transaction.atomic
def post_update(item: Item, author: RealmMembership, body: str, mentions=()) -> ItemUpdate:
    body = (body or "").strip()
    if not body:
        raise ValidationError({"body": "Write something."})
    if len(body) > 10000:
        raise ValidationError({"body": "Keep it to 10,000 characters."})
    from apps.projects.access import can

    project = item.board.project
    ids = []
    for pk in list(mentions)[:30]:
        person = RealmMembership.objects.in_realm(item.realm_id).active().by_id(pk)
        if person is not None and person.pk not in ids and can(person, project, "view"):
            ids.append(person.pk)
    update = ItemUpdate.objects.create(
        realm_id=item.realm_id, item=item, author=author, body=body, mentions=ids
    )
    actor = Actor(membership=author)
    _activity(item, actor, ItemActivity.Kind.UPDATE, new_text=_short(body)).save()
    Item.objects.in_realm(item.realm_id).filter(pk=item.pk).update(updated_at=timezone.now())
    recipients = [pk for pk in ids if pk != author.pk]
    if recipients:
        notify.send(
            item.realm_id,
            recipients,
            kind="mention",
            title=f"{author.display_name} mentioned you on {item.name}",
            body=_short(body),
            link=_link(item),
            actor=author.display_name,
        )
    _changed(item.board, [item.pk])
    return update


# --- views -----------------------------------------------------------------------------------

VIEW_KEYS = {"search", "filters", "sort", "hidden", "kanban_column", "group_by"}


def _clean_view_config(board: Board, config) -> dict:
    if not isinstance(config, dict):
        raise ValidationError({"config": "Send the view's settings."})
    clean = {k: v for k, v in config.items() if k in VIEW_KEYS}
    if "kanban_column" in clean and clean["kanban_column"]:
        column = BoardContext(board).by_key.get(clean["kanban_column"])
        if column is None or column.type != "status":
            raise ValidationError({"config": "A kanban is grouped by a status column."})
    if len(str(clean)) > 10000:
        raise ValidationError({"config": "That view is too large."})
    return clean


@transaction.atomic
def create_view(board: Board, name: str, kind: str, config, by) -> BoardView:
    if kind not in BoardView.Kind.values:
        raise ValidationError({"kind": "Choose table or kanban."})
    view = BoardView.objects.create(
        realm_id=board.realm_id,
        board=board,
        name=(name or "View").strip()[:60],
        kind=kind,
        config=_clean_view_config(board, config or {}),
        position=_next_position(BoardView.objects.in_realm(board.realm_id).of_board(board)),
        created_by=by,
    )
    _changed(board)
    return view


@transaction.atomic
def update_view(view: BoardView, **fields) -> BoardView:
    if "config" in fields:
        view.config = _clean_view_config(view.board, fields["config"])
    if "name" in fields:
        view.name = (fields["name"] or "View").strip()[:60]
    if "position" in fields:
        view.position = fields["position"]
    view.save()
    _changed(view.board)
    return view


@transaction.atomic
def delete_view(view: BoardView) -> None:
    board = view.board
    if BoardView.objects.in_realm(board.realm_id).of_board(board).count() <= 1:
        raise ValidationError({"detail": "A board keeps at least one view."})
    view.delete()
    _changed(board)
