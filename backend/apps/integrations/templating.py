"""Filling a request template from the call context.

Deliberately tiny, so a definition can only put known values into a fixed structure:
- `"{{ site.latitude }}"` as a whole string is replaced by the value itself (a number stays a
  number); `"{{ site.latitude | string }}"` makes it a string.
- Placeholders inside longer text are put in as text: `"Site {{ site.name }}"`.
- `{"$each": "sites", "item": {...}}` becomes a list, one `item` per element, with that element
  available as `item` (`"{{ item.latitude }}"`).
- Paths are dotted names looked up in the context; there are no expressions, calls or filters
  beyond `string`.

The context has `site` (the first site), `sites`, `products`, `product_codes` and `settings` (the
connection's non-secret fields). Secrets are never in it: auth placements add them (engine.py).
"""

import re
from typing import Any

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*(\|\s*string\s*)?\}\}")


class TemplateError(ValueError):
    pass


def lookup(context: dict, path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise TemplateError(f"{path!r} isn't available here")
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(value)
    return str(value)


def render(template: Any, context: dict) -> Any:
    if isinstance(template, str):
        whole = PLACEHOLDER.fullmatch(template.strip())
        if whole:
            value = lookup(context, whole.group(1))
            return _text(value) if whole.group(2) else value
        return PLACEHOLDER.sub(lambda m: _text(lookup(context, m.group(1))), template)
    if isinstance(template, list):
        return [render(item, context) for item in template]
    if isinstance(template, dict):
        if "$each" in template:
            items = lookup(context, template["$each"])
            if not isinstance(items, list):
                raise TemplateError(f"{template['$each']!r} isn't a list")
            return [render(template.get("item"), {**context, "item": item}) for item in items]
        return {key: render(value, context) for key, value in template.items()}
    return template
