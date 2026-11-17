"""Permissions and the built-in roles: the one place that says who may do what.

Access is always checked by permission code, never by a role's name or key. A spec that adds a
capability adds its codes to PERMISSIONS and says which built-in roles get them in
SYSTEM_ROLES. Every company has the built-in roles as `Role` rows (models.py), but a built-in
role's permissions are read from here, so a change reaches every company without touching data.
Custom roles (a later spec) keep their own list on the row instead.

Admin always has every permission, including ones added later.
"""

from dataclasses import dataclass, field

# code -> what it lets someone do. Shown next to roles, so written for the people choosing one.
PERMISSIONS: dict[str, str] = {
    "users.view": "See the company's users",
    "users.manage": "Add, edit and remove users, and change their roles",
    "integrations.view": "See the company's provider connections and their products",
    "integrations.manage": "Connect providers, change their credentials, and test or sync them",
    "integrations.logs": "See the requests made to providers and their answers",
    "feasibilities.view": "See feasibility runs and their results, and export them",
    "feasibilities.run": "Start, cancel and retry feasibility runs",
}

ADMIN = "admin"


@dataclass(frozen=True)
class SystemRole:
    name: str
    description: str
    permissions: frozenset[str] = field(default_factory=frozenset)


SYSTEM_ROLES: dict[str, SystemRole] = {
    ADMIN: SystemRole("Admin", "Runs the company's account. Can do everything."),
    "project_manager": SystemRole(
        "Project manager",
        "Plans and runs projects. Can see the company's users and integrations, and run "
        "feasibilities.",
        frozenset(
            {
                "users.view",
                "integrations.view",
                "integrations.logs",
                "feasibilities.view",
                "feasibilities.run",
            }
        ),
    ),
    "viewer": SystemRole("Viewer", "Read-only access.", frozenset({"feasibilities.view"})),
}


def system_role_permissions(key: str) -> frozenset[str]:
    if key == ADMIN:
        return frozenset(PERMISSIONS)
    role = SYSTEM_ROLES.get(key)
    return role.permissions & frozenset(PERMISSIONS) if role else frozenset()
