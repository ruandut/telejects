"""What a websocket may send, declared by each app next to its own data.

An app that pushes live data has `live.py` exposing `TOPICS = {name: Topic(...)}`. The consumer
(consumers.py) finds them like the worker finds tasks, so this platform app never imports a
domain app. A topic says:
- `permission`: the code a subscriber needs, checked on subscribing and again before every send;
- `subject`: whether a subscription names one thing (a run) and, if so, `authorize`, which looks
  it up through the app's scoped queryset (another company's is refused like a missing one);
- `render`: builds what a subscriber receives for the rows that changed, with the same scoped
  queryset and serializer as the matching API endpoint. Without it the topic only says
  "changed", and the tab refetches.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from importlib import import_module
from importlib.util import find_spec

from django.apps import apps


@dataclass(frozen=True)
class Topic:
    permission: str
    subject: bool = False
    # (membership, subject id) -> whether it exists for them. Required when subject is True.
    authorize: Callable | None = None
    # (membership, subject id or None, changed ids) -> the data to send, or None for "changed".
    render: Callable | None = None


@cache
def topics() -> dict[str, Topic]:
    found: dict[str, Topic] = {}
    for config in apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        module_name = f"{config.name}.live"
        if find_spec(module_name) is None:
            continue
        for name, topic in getattr(import_module(module_name), "TOPICS", {}).items():
            if name in found:
                raise RuntimeError(f"Two apps declare the live topic {name!r}")
            found[name] = topic
    return found
