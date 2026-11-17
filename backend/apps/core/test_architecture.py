"""Apps import downward only. A new app is added here and to INSTALLED_APPS."""

import ast
from pathlib import Path

import pytest
from django.apps import apps

APPS_DIR = Path(__file__).resolve().parent.parent

# app -> the other apps it may import. Platform apps never import domain apps.
ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    "core": set(),
    "realms": {"core"},
    "jobs": {"core"},
    "accounts": {"core", "realms", "jobs"},
    "users": {"core", "accounts", "realms", "jobs"},
}


def _our_apps() -> list[str]:
    return sorted(c.label for c in apps.get_app_configs() if c.name.startswith("apps."))


def _imported_apps(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        for name in names:
            parts = name.split(".")
            if parts[0] == "apps" and len(parts) > 1:
                found.add(parts[1])
    return found


def test_every_app_declares_its_dependencies():
    assert _our_apps() == sorted(ALLOWED_DEPENDENCIES)


@pytest.mark.parametrize("app", sorted(ALLOWED_DEPENDENCIES))
def test_app_only_imports_what_it_may(app):
    allowed = ALLOWED_DEPENDENCIES[app] | {app}
    for path in (APPS_DIR / app).rglob("*.py"):
        # Tests may reach across apps to set up data; migrations are generated.
        if path.name.startswith("test_") or "migrations" in path.parts:
            continue
        extra = _imported_apps(path) - allowed
        assert not extra, f"{path.relative_to(APPS_DIR)} imports {sorted(extra)}"
