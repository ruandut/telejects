"""Automations react to the boards' signals (boards never imports this app)."""

from django.dispatch import receiver

from apps.boards import signals
from apps.boards.models import Board

from . import services, templates


@receiver(signals.item_created, dispatch_uid="automations-item-created")
def on_created(sender, item, actor, **kwargs):
    services.handle("created", item, actor)


@receiver(signals.values_changed, dispatch_uid="automations-values-changed")
def on_values(sender, item, changes, actor, **kwargs):
    services.handle("values", item, actor, changes=changes)


@receiver(signals.item_moved, dispatch_uid="automations-item-moved")
def on_moved(sender, item, from_group, actor, **kwargs):
    services.handle("moved", item, actor, from_group=from_group)


@receiver(signals.board_created, dispatch_uid="automations-board-template")
def on_board(sender, board: Board, template, actor, **kwargs):
    templates.install(board, template, actor.membership)
