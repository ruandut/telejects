"""Board templates: the groups, columns and views a new board starts with (0007)."""

PROVINCES = [
    "Gauteng",
    "Western Cape",
    "KwaZulu-Natal",
    "Eastern Cape",
    "Free State",
    "Limpopo",
    "Mpumalanga",
    "North West",
    "Northern Cape",
]


def _labels(*rows):
    return [
        {"id": key, "label": label, "colour": colour, "done": done}
        for key, label, colour, done in rows
    ]


def _options(*names):
    return [
        {"id": f"o{i}", "label": n, "colour": "grey", "done": False} for i, n in enumerate(names)
    ]


TEMPLATES = {
    # Nothing at all: for boards built from a file (file_import.py). Not offered as a template.
    "_empty": {
        "name": "Empty",
        "description": "",
        "board": "Board",
        "groups": [],
        "columns": [],
        "status_column": "",
        "due_column": "",
    },
    "blank": {
        "name": "Blank board",
        "description": "A status, an owner and a date, ready for your own columns.",
        "board": "Board",
        "groups": [("To do", "blue"), ("Done", "green")],
        "columns": [
            ("status", "Status", "status", {}),
            ("owner", "Owner", "people", {}),
            ("date", "Date", "date", {}),
        ],
        "status_column": "status",
        "due_column": "date",
    },
    "site_rollout": {
        "name": "Site rollout",
        "description": "Sites from feasibility to live: status, location, provider, service, "
        "fees, install dates and contacts.",
        "board": "Sites",
        "groups": [("New sites", "blue"), ("In progress", "amber"), ("Completed", "green")],
        "columns": [
            (
                "status",
                "Status",
                "status",
                {
                    "labels": _labels(
                        ("new", "Not started", "grey", False),
                        ("feas", "Feasibility", "blue", False),
                        ("quoted", "Quoted", "purple", False),
                        ("ordered", "Ordered", "teal", False),
                        ("survey", "Survey booked", "indigo", False),
                        ("install", "Installing", "amber", False),
                        ("stuck", "Stuck", "red", False),
                        ("live", "Live", "green", True),
                        ("cancelled", "Cancelled", "brown", False),
                    )
                },
            ),
            ("assignee", "Assignee", "people", {}),
            ("location", "Location", "location", {}),
            ("region", "Region", "dropdown", {"options": _options(*PROVINCES)}),
            (
                "provider",
                "Provider",
                "dropdown",
                {"options": _options("MTN", "Vodacom", "Herotel", "Link Africa", "Other")},
            ),
            (
                "service",
                "Service",
                "dropdown",
                {"options": _options("Fibre", "LTE", "5G", "Microwave", "Satellite")},
            ),
            ("speed", "Speed", "number", {"unit": "Mbps", "unit_position": "right"}),
            ("fee", "Monthly fee", "number", {"unit": "R", "decimals": 2}),
            ("term", "Term (months)", "number", {}),
            (
                "contract",
                "Contract value",
                "formula",
                {"expression": "{Monthly fee} * {Term (months)}", "unit": "R"},
            ),
            ("ordered", "Ordered", "date", {}),
            ("install", "Install date", "date", {}),
            ("golive", "Go-live", "date", {}),
            ("contact", "Site contact", "text", {}),
            ("phone", "Contact phone", "phone", {}),
            ("email", "Contact email", "email", {}),
            ("notes", "Notes", "long_text", {}),
            ("updated", "Last updated", "updated", {}),
        ],
        "status_column": "status",
        "due_column": "install",
    },
}


def catalogue() -> list[dict]:
    return [
        {
            "key": key,
            "name": t["name"],
            "description": t["description"],
            "columns": [c[1] for c in t["columns"]],
        }
        for key, t in TEMPLATES.items()
        if not key.startswith("_")
    ]
