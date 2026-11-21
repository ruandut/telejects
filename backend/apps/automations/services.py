"""Running automations (0007): the only place that writes automations and their runs.

Item events (created, a column changed, moved) come from the boards' signals, inside the
person's transaction. Each matching automation runs right away in its own savepoint, so a rule
that fails is logged on its run and never undoes the person's edit. Changes an automation makes
can set off others, up to MAX_DEPTH in a chain.

Timers come from `tick`, every minute on Hatchet: dates that arrive, schedules, and actions that
were told to wait. Each fires once per item per date or occurrence (`trigger_key`).
"""

import datetime as dt
import logging
import re
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.boards import services as boards
from apps.boards.column_types import TYPES, Invalid, type_of
from apps.boards.context import BoardContext
from apps.boards.models import Board, Group, Item
from apps.notifications import services as notify
from apps.projects.access import can
from apps.realms.models import RealmMembership

from .models import Automation, AutomationRun
from .recipes import MAX_DEPTH, TIMER_TRIGGERS, Checker, delay_of

logger = logging.getLogger(__name__)


class ActionFailed(Exception):
    pass


# --- writing automations ---------------------------------------------------------------------


def _checked(board, membership, data) -> dict:
    check = Checker(board, membership)
    out = {}
    if "name" in data:
        name = str(data["name"] or "").strip()[:120]
        if not name:
            raise ValidationError({"name": "Give the automation a name."})
        out["name"] = name
    if "trigger" in data:
        out["trigger"] = check.trigger(data["trigger"])
    if "conditions" in data:
        out["conditions"] = check.conditions(data["conditions"])
    if "actions" in data:
        out["actions"] = check.actions(data["actions"])
    if "delay" in data:
        out["delay"] = check.delay(data["delay"])
    if "enabled" in data:
        out["enabled"] = bool(data["enabled"])
    return out


def _fresh_state(trigger: dict, now=None) -> dict:
    """A schedule starts with its latest past occurrence counted as fired, so creating one
    at 09:00 for 08:00 waits for the next one."""
    if trigger.get("type") != "schedule":
        return {}
    occurrence = schedule_occurrence(trigger, now or timezone.now())
    return {"last": occurrence} if occurrence else {}


@transaction.atomic
def create_automation(board: Board, membership, data: dict) -> Automation:
    for field in ("name", "trigger", "actions"):
        if field not in data:
            raise ValidationError({field: "This is needed."})
    fields = _checked(board, membership, data)
    return Automation.objects.create(
        realm_id=board.realm_id,
        board=board,
        created_by=membership,
        state=_fresh_state(fields["trigger"]),
        **fields,
    )


@transaction.atomic
def update_automation(automation: Automation, membership, data: dict) -> Automation:
    fields = _checked(automation.board, membership, data)
    if "trigger" in fields and fields["trigger"] != automation.trigger:
        automation.state = _fresh_state(fields["trigger"])
    for name, value in fields.items():
        setattr(automation, name, value)
    automation.save()
    if fields.get("enabled") is False:
        AutomationRun.objects.in_realm(automation.realm_id).of_automation(automation).filter(
            status=AutomationRun.Status.SCHEDULED
        ).update(status=AutomationRun.Status.CANCELLED, message="The automation was switched off.")
    return automation


def delete_automation(automation: Automation) -> None:
    automation.delete()


# --- matching --------------------------------------------------------------------------------


def _trigger_matches(trigger, event, changes, from_group, item) -> bool:
    kind = trigger["type"]
    if event == "created":
        return kind == "item_created"
    if event == "moved":
        return kind == "item_moved" and trigger.get("group") in (None, item.group_id)
    if event == "values":
        if kind == "column_changed":
            return trigger.get("column") is None or trigger["column"] in changes
        if kind == "status_changed" and trigger["column"] in changes:
            new = changes[trigger["column"]][1]
            return new is not None and (not trigger["to"] or new in trigger["to"])
    return False


def conditions_hold(automation, item, ctx: BoardContext) -> bool:
    values = ctx.full_values([item])[item.pk]
    for condition in automation.conditions:
        if condition["column"] == "group":
            same = item.group_id == condition["value"]
            if same != (condition["op"] == "is"):
                return False
            continue
        column = ctx.by_key.get(condition["column"])
        if column is None:
            return False
        if not type_of(column).matches(
            values.get(column.key), condition["op"], condition["value"], column, ctx
        ):
            return False
    return True


def handle(event: str, item: Item, actor: boards.Actor, changes=None, from_group=None) -> None:
    """Called by the boards' signals after an item changed."""
    automations = list(
        Automation.objects.in_realm(item.realm_id)
        .enabled()
        .filter(board_id=item.board_id)
        .exclude(trigger__type__in=list(TIMER_TRIGGERS))
    )
    if not automations:
        return
    matching = [
        a
        for a in automations
        if _trigger_matches(a.trigger, event, changes or {}, from_group, item)
    ]
    for automation in matching:
        fire(automation, item, actor)


def fire(automation, item, actor: boards.Actor, trigger_key: str = "") -> AutomationRun | None:
    """Conditions hold: run it now, or schedule it when it waits."""
    item = Item.objects.in_realm(item.realm_id).select_related("board__project").get(pk=item.pk)
    ctx = BoardContext(item.board)
    if not conditions_hold(automation, item, ctx):
        return None
    depth = actor.depth + 1 if actor.automation_id else 1
    by = actor.membership
    if depth > MAX_DEPTH:
        return _record(
            automation,
            item,
            AutomationRun.Status.SKIPPED,
            f"Stopped: automations set each other off {MAX_DEPTH} times in a row.",
            trigger_key=trigger_key,
            depth=depth,
            by=by,
        )
    if automation.delay:
        return _record(
            automation,
            item,
            AutomationRun.Status.SCHEDULED,
            "",
            trigger_key=trigger_key,
            depth=depth,
            by=by,
            due_at=timezone.now() + delay_of(automation.delay),
        )
    return run_now(automation, item, depth, by, trigger_key=trigger_key)


def _record(automation, item, status, message, run=None, **fields) -> AutomationRun | None:
    now = timezone.now()
    finished = None if status == AutomationRun.Status.SCHEDULED else now
    if run is None:
        try:
            with transaction.atomic():
                run = AutomationRun.objects.create(
                    realm_id=automation.realm_id,
                    automation=automation,
                    item=item,
                    item_name=item.name[:255] if item else "",
                    status=status,
                    message=message[:500],
                    finished_at=finished,
                    **fields,
                )
        except IntegrityError:
            return None  # this item already fired for this date or occurrence
    else:
        run.status, run.message, run.finished_at = status, message[:500], finished
        run.save(update_fields=["status", "message", "finished_at"])
    if status in (AutomationRun.Status.DONE, AutomationRun.Status.FAILED):
        Automation.objects.in_realm(automation.realm_id).filter(pk=automation.pk).update(
            run_count=F("run_count") + 1, last_run_at=now
        )
        automation.run_count += 1
    return run


def run_now(automation, item, depth, by, trigger_key="", run=None) -> AutomationRun | None:
    if run is None and trigger_key:
        # Claim the key first, so two ticks can't both fire it.
        run = _record(
            automation,
            item,
            AutomationRun.Status.SCHEDULED,
            "",
            trigger_key=trigger_key,
            depth=depth,
            by=by,
            due_at=timezone.now(),
        )
        if run is None:
            return None
    actor = boards.Actor(automation_id=automation.pk, automation_name=automation.name, depth=depth)
    try:
        with transaction.atomic():
            for action in automation.actions:
                item = _perform(action, automation, item, actor, by)
    except (ActionFailed, ValidationError, Invalid, Board.DoesNotExist, Item.DoesNotExist) as error:
        return _record(
            automation,
            item,
            AutomationRun.Status.FAILED,
            _reason(error),
            run=run,
            depth=depth,
            by=by,
        )
    except Exception as error:  # a broken rule must never break the person's edit
        logger.exception("Automation %s failed", automation.pk)
        return _record(
            automation,
            item,
            AutomationRun.Status.FAILED,
            f"Unexpected error: {type(error).__name__}",
            run=run,
            depth=depth,
            by=by,
        )
    return _record(automation, item, AutomationRun.Status.DONE, "", run=run, depth=depth, by=by)


def _reason(error) -> str:
    if isinstance(error, ValidationError):
        detail = error.detail
        while isinstance(detail, dict) and detail:
            detail = next(iter(detail.values()))
        while isinstance(detail, list) and detail:
            detail = detail[0]
        return str(detail)
    if isinstance(error, (Board.DoesNotExist, Item.DoesNotExist)):
        return "What it points at no longer exists."
    return str(error)


# --- actions ---------------------------------------------------------------------------------


def _resolve(value, column, item, by):
    if column.type == "date" and isinstance(value, dict) and "today_plus" in value:
        return (timezone.localdate() + dt.timedelta(days=value["today_plus"])).isoformat()
    if column.type == "people" and value == "trigger_person":
        return [by.pk] if by is not None else None
    if column.type == "people" and value == "creator":
        return [item.created_by_id] if item.created_by_id else None
    return value


def _text_of(item, key, ctx) -> str:
    if key == "name":
        return item.name
    column = ctx.by_key.get(key)
    if column is None:
        return ""
    values = ctx.full_values([item])[item.pk]
    return ctx.text(column, values.get(key))


def render(template: str, item, ctx) -> str:
    """{name} and {Column title} replaced by the item's values, as they read."""

    def swap(match):
        title = match.group(1).strip()
        if title.lower() == "name":
            return item.name
        column = next((c for c in ctx.columns if c.title.lower() == title.lower()), None)
        return _text_of(item, column.key, ctx) if column else match.group(0)

    return re.sub(r"\{([^{}]{1,80})\}", swap, template)


def _copy_value(source_key, source_item, source_ctx, target_column, target_ctx):
    """A value from one column for another, converted the way a person would type it."""
    if source_key == "name":
        raw = source_item.name
    else:
        source = source_ctx.by_key.get(source_key)
        if source is None:
            raise ActionFailed("The column to copy from no longer exists.")
        raw = source_item.values.get(source_key)
        if source.type != target_column.type or source.type in ("status", "dropdown"):
            raw = (
                source_ctx.text(
                    source, source_ctx.full_values([source_item])[source_item.pk].get(source_key)
                )
                or None
            )
            if source.type == "people" and target_column.type == "people":
                raw = source_item.values.get(source_key)
    try:
        return type_of(target_column).clean(raw, target_column, target_ctx)
    except Invalid as error:
        raise ActionFailed(f"{target_column.title}: {error}") from error


def _perform(action, automation, item, actor, by) -> Item:
    item = Item.objects.in_realm(item.realm_id).select_related("board__project").get(pk=item.pk)
    if item.archived_at is not None and action["type"] != "archive_item":
        raise ActionFailed("The item is archived.")
    ctx = BoardContext(item.board)
    kind = action["type"]
    if kind in ("set_value", "clear_value", "increment"):
        column = ctx.by_key.get(action["column"])
        if column is None:
            raise ActionFailed("The column it sets no longer exists.")
        if kind == "clear_value":
            value = None
        elif kind == "increment":
            current = TYPES["number"].number(item.values.get(column.key), column) or Decimal(0)
            value = str(current + Decimal(action["by"]))
        else:
            value = _resolve(action["value"], column, item, by)
        return boards.set_values(item, {column.key: value}, actor)
    if kind == "copy_value":
        if action["to"] == "name":
            text = _text_of(item, action["from"], ctx)
            return boards.rename_item(item, text, actor) if text else item
        target = ctx.by_key.get(action["to"])
        if target is None:
            raise ActionFailed("The column to copy into no longer exists.")
        value = _copy_value(action["from"], item, ctx, target, ctx)
        return boards.set_values(item, {target.key: value}, actor)
    if kind == "move_to_group":
        if (
            not Group.objects.in_realm(item.realm_id)
            .filter(pk=action["group"], board_id=item.board_id)
            .exists()
        ):
            raise ActionFailed("The group it moves to no longer exists.")
        if item.group_id == action["group"]:
            return item
        return boards.move_item(item, group=action["group"], actor=actor)
    if kind == "archive_item":
        return boards.archive_item(item, actor)
    if kind == "notify":
        _notify(action, automation, item, ctx, by)
        return item
    if kind == "create_item":
        target = (
            Board.objects.in_realm(item.realm_id).select_related("project").get(pk=action["board"])
        )
        target_ctx = BoardContext(target)
        values = {}
        for pair in action["copy"]:
            column = target_ctx.by_key.get(pair["to"])
            if column is None:
                raise ActionFailed("A column it copies into no longer exists.")
            values[column.key] = _copy_value(pair["from"], item, ctx, column, target_ctx)
        created = boards.create_item(
            target,
            render(action["name"], item, ctx) or item.name,
            group=action.get("group"),
            values={k: v for k, v in values.items() if v is not None},
            actor=actor,
        )
        link = action.get("link_column")
        if link and link in ctx.by_key:
            linked = list(item.values.get(link) or []) + [created.pk]
            return boards.set_values(item, {link: linked}, actor)
        return item
    raise ActionFailed(f"Unknown action {kind}")


def _notify(action, automation, item, ctx, by):
    people = set(action.get("members") or [])
    if action.get("people_column"):
        people |= set(item.values.get(action["people_column"]) or [])
    if action.get("trigger_person") and by is not None:
        people.add(by.pk)
    if not people:
        return
    message = render(action.get("message") or "", item, ctx).strip()
    project = item.board.project
    notify.send(
        item.realm_id,
        sorted(people),
        kind="automation",
        title=message or f"{automation.name}: {item.name}",
        body=f"{item.name} on {item.board.name}",
        link={"project": project.pk, "board": item.board_id, "item": item.pk},
        actor=f"Automation: {automation.name}",
        allowed=lambda membership: can(membership, project, "view"),
    )


# --- timers ----------------------------------------------------------------------------------


def _at(local_now, hhmm: str) -> bool:
    hour, minute = (int(p) for p in hhmm.split(":"))
    return (local_now.hour, local_now.minute) >= (hour, minute)


def schedule_occurrence(trigger: dict, now) -> str | None:
    """Today's occurrence ("2026-11-23T08:00") if it is due by now, else None."""
    local = timezone.localtime(now)
    today = local.date()
    every = trigger["every"]
    if every == "weekday" and today.weekday() >= 5:
        return None
    if every == "week" and today.weekday() != trigger.get("weekday"):
        return None
    if every == "month" and today.day != trigger.get("day"):
        return None
    if not _at(local, trigger["time"]):
        return None
    return f"{today.isoformat()}T{trigger['time']}"


def _target_date(trigger, today) -> dt.date:
    days = dt.timedelta(days=trigger.get("days", 0))
    return {"before": today + days, "after": today - days}.get(trigger["when"], today)


def due_timers(now=None) -> list[int]:
    """Every company's enabled timer automations (the minutely tick looks at each in its own
    company)."""
    return list(
        Automation.objects.across_realms()
        .enabled()
        .triggered_by(*TIMER_TRIGGERS)
        .values_list("id", flat=True)
    )


def due_waiting(now=None) -> list[tuple[int, int]]:
    """Every company's waiting actions whose time has come: (realm id, run id)."""
    now = now or timezone.now()
    return list(AutomationRun.objects.across_realms().due(now).values_list("realm_id", "id")[:1000])


def run_timer(automation_id: int, now=None) -> int:
    """Fire one timer automation for every item that is due; returns how many fired."""
    now = now or timezone.now()
    automation = Automation.objects.across_realms().filter(pk=automation_id, enabled=True).first()
    if automation is None:
        return 0
    realm_id = automation.realm_id
    trigger = automation.trigger
    local = timezone.localtime(now)
    items = Item.objects.in_realm_id(realm_id).filter(board_id=automation.board_id).live()
    fired = 0
    if trigger["type"] == "date_arrives":
        if not _at(local, trigger["time"]):
            return 0
        target = _target_date(trigger, local.date()).isoformat()
        column = BoardContext(automation.board).by_key.get(trigger["column"])
        if column is None:
            return 0
        lookup = f"values__{column.key}" + ("__end" if column.type == "timeline" else "")
        key = f"date:{target}"
        for item in items.filter(**{lookup: target}):
            if not _claimable(automation, item, key):
                continue
            with transaction.atomic():
                if fire(automation, item, boards.SYSTEM, key):
                    fired += 1
        return fired
    occurrence = schedule_occurrence(trigger, now)
    if occurrence is None or automation.state.get("last") == occurrence:
        return 0
    with transaction.atomic():
        locked = Automation.objects.in_realm_id(realm_id).select_for_update().get(pk=automation.pk)
        if locked.state.get("last") == occurrence:
            return 0
        locked.state = {**locked.state, "last": occurrence}
        locked.save(update_fields=["state"])
    key = f"schedule:{occurrence}"
    for item in items:
        with transaction.atomic():
            if fire(automation, item, boards.SYSTEM, key):
                fired += 1
    return fired


def _claimable(automation, item, key) -> bool:
    return (
        not AutomationRun.objects.in_realm(automation.realm_id)
        .filter(automation=automation, item=item, trigger_key=key)
        .exists()
    )


def run_waiting(realm_id: int, run_id: int) -> AutomationRun | None:
    """An action told to wait: run it now, unless its automation was switched off, the item
    is gone, or its conditions no longer hold."""
    with transaction.atomic():
        run = (
            AutomationRun.objects.in_realm_id(realm_id)
            .select_for_update(skip_locked=True, of=("self",))
            .select_related("automation__board", "item")
            .filter(pk=run_id, status=AutomationRun.Status.SCHEDULED)
            .first()
        )
        if run is None:
            return None
        automation = run.automation
        if not automation.enabled:
            return _record(
                automation,
                run.item,
                AutomationRun.Status.CANCELLED,
                "The automation was switched off.",
                run=run,
            )
        item = run.item
        if item is None or item.archived_at is not None:
            return _record(
                automation,
                item,
                AutomationRun.Status.CANCELLED,
                "The item was deleted or archived.",
                run=run,
            )
        if not conditions_hold(automation, item, BoardContext(automation.board)):
            return _record(
                automation,
                item,
                AutomationRun.Status.SKIPPED,
                "Its conditions no longer hold.",
                run=run,
            )
        return run_now(automation, item, run.depth, run.by, run=run)


def tick(now=None) -> dict:
    """What the minutely Hatchet task does."""
    now = now or timezone.now()
    timers = sum(run_timer(pk, now) for pk in due_timers(now))
    waiting = sum(1 for realm_id, pk in due_waiting(now) if run_waiting(realm_id, pk))
    return {"timers": timers, "waiting": waiting}


def membership_by_id(realm_id, pk) -> RealmMembership | None:
    return RealmMembership.objects.in_realm(realm_id).by_id(pk)
