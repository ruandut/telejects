"""Signals the automations app listens to, so boards never imports it (0007). Each is sent
after the change is saved, inside the same transaction, with the Actor that made it.

- `item_created(item, actor)`
- `values_changed(item, changes, actor)`: changes is {column key: (old, new)}
- `item_moved(item, from_group, actor)`: from_group is the old group's id
- `board_created(board, template, actor)`
"""

from django.dispatch import Signal

item_created = Signal()
values_changed = Signal()
item_moved = Signal()
board_created = Signal()
