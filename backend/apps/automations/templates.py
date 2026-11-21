"""Automations a board template starts with (0007)."""

from rest_framework.exceptions import ValidationError

from apps.boards.context import BoardContext

from . import services

TEMPLATES = {
    "site_rollout": [
        {
            "name": "Stamp the go-live date",
            "trigger": {"type": "status_changed", "column": "status", "to": ["live"]},
            "actions": [{"type": "set_value", "column": "golive", "value": {"today_plus": 0}}],
        },
        {
            "name": "Stamp the order date",
            "trigger": {"type": "status_changed", "column": "status", "to": ["ordered"]},
            "actions": [{"type": "set_value", "column": "ordered", "value": {"today_plus": 0}}],
        },
        {
            "name": "Move live sites to Completed",
            "trigger": {"type": "status_changed", "column": "status", "to": ["live"]},
            "actions": [{"type": "move_to_group", "group": "Completed"}],
        },
        {
            "name": "Remind the assignee before installation",
            "trigger": {
                "type": "date_arrives",
                "column": "install",
                "when": "before",
                "days": 2,
                "time": "08:00",
            },
            "actions": [
                {
                    "type": "notify",
                    "people_column": "assignee",
                    "message": "{name} installs on {Install date}",
                }
            ],
        },
    ]
}


def install(board, template: str, membership) -> None:
    recipes = TEMPLATES.get(template)
    if not recipes:
        return
    groups = {g.name: g.pk for g in board.groups.all()}
    keys = set(BoardContext(board).by_key)
    for recipe in recipes:
        actions = []
        for action in recipe["actions"]:
            if action["type"] == "move_to_group":
                action = {**action, "group": groups.get(action["group"])}
            actions.append(action)
        if recipe["trigger"].get("column") not in keys:
            continue
        try:
            services.create_automation(board, None, {**recipe, "actions": actions})
        except ValidationError:
            continue  # the template's board changed; skip the rule rather than the board
