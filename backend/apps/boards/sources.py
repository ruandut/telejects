"""A board made from a feasibility run (0007): one item per site, with what the providers said.

The board starts from the Site rollout template and gains:
- Feasibility (status): the best answer at the site across every product checked: Available,
  Near-net, Coverage only, Not available, or Pending while a check is still open;
- Available products (dropdown): the products that are available there;
- Feasibility results (long text): every product's answer, with bandwidths;
- a text column per extra column of the uploaded file (an address, a site reference), so
  nothing from the original list is lost.
The values are a snapshot taken when the board is made; the run itself is linked from the board.
"""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.feasibilities.models import FeasibilityRun, RunSite
from apps.integrations.canonical import STATUS_LABELS, Status

from . import services
from .context import BoardContext

MAX_SITES = services.MAX_IMPORT_ROWS
MAX_EXTRA_COLUMNS = 20

# Best first: a site's overall answer is the best any product gave.
RANK = [Status.AVAILABLE, Status.NEAR_NET, Status.COVERAGE_ONLY, Status.NOT_AVAILABLE]
# Label ids are short: a column's label ids are at most 12 characters (column_types.Labels).
LABEL_IDS = {
    Status.AVAILABLE: "available",
    Status.NEAR_NET: "near_net",
    Status.COVERAGE_ONLY: "coverage",
    Status.NOT_AVAILABLE: "not_avail",
}
COLOURS = {
    Status.AVAILABLE: "green",
    Status.NEAR_NET: "amber",
    Status.COVERAGE_ONLY: "blue",
    Status.NOT_AVAILABLE: "red",
}
LABELS = [
    *(
        {"id": LABEL_IDS[s], "label": STATUS_LABELS[s], "colour": COLOURS[s], "done": False}
        for s in RANK
    ),
    {"id": "pending", "label": "Pending", "colour": "grey", "done": False},
]


def _product_label(product) -> str:
    return f"{product.connection.name}: {product.name}"


def _bandwidths(result) -> str:
    shown = []
    for low, high in result.bandwidths or []:
        if low and high and low != high:
            shown.append(f"{low}-{high} Mbps")
        elif high or low:
            shown.append(f"{high or low} Mbps")
    return f" ({', '.join(shown)})" if shown else ""


def _summary(site, labels) -> tuple[str, list[str], str]:
    """(overall status id, available product labels, results text) for one site."""
    results = list(site.results.all())
    if not results:
        return "pending", [], ""
    best = min(RANK.index(Status(r.status)) for r in results)
    available, lines = [], []
    for r in results:
        label = labels.get(r.product_id, "Product")
        if r.status == Status.AVAILABLE and label not in available:
            available.append(label)
        variant = f" - {r.variant_name}" if r.variant_name else ""
        lines.append(f"{label}{variant}: {STATUS_LABELS[Status(r.status)]}{_bandwidths(r)}")
    return LABEL_IDS[RANK[best]], available, "\n".join(lines)


@transaction.atomic
def board_from_run(project, run: FeasibilityRun, name: str, actor: services.Actor):
    if run.realm_id != project.realm_id:
        raise ValidationError({"feasibility_run": "Choose one of this company's runs."})
    sites = RunSite.objects.in_realm(run.realm_id).of_run(run)
    if sites.count() > MAX_SITES:
        raise ValidationError({"feasibility_run": f"A board holds at most {MAX_SITES:,} sites."})
    board = services.create_board(project, name or run.name, "site_rollout", actor)
    board.feasibility_run = run
    board.save(update_fields=["feasibility_run"])

    products = list(
        run.products.all().select_related("connection").order_by("connection__name", "name")
    )
    labels = {p.id: _product_label(p) for p in products}
    feasibility = services.create_column(
        board, "Feasibility", "status", {"labels": LABELS}, after="status"
    )
    offered = services.create_column(
        board,
        "Available products",
        "dropdown",
        {
            "options": [
                {"id": f"p{p.id}", "label": labels[p.id], "colour": "grey", "done": False}
                for p in products
            ]
        },
        after=feasibility.key,
    )
    details = services.create_column(board, "Feasibility results", "long_text", after=offered.key)
    used = {(run.mapping or {}).get(k) for k in ("name", "latitude", "longitude")}
    extras = {}
    for column in [c for c in (run.columns or []) if c not in used][:MAX_EXTRA_COLUMNS]:
        extras[column] = services.create_column(board, str(column)[:80], "text").key

    ctx = BoardContext(board, actor.membership)
    group = ctx.board.groups.order_by("position", "id").first()
    for site in sites.with_results():
        status, available, text = _summary(site, labels)
        values = {
            "location": {"lat": str(site.latitude), "lng": str(site.longitude)},
            feasibility.key: status,
            offered.key: available or None,
            details.key: text or None,
        }
        for column, key in extras.items():
            cell = str((site.row or {}).get(column) or "").strip()
            if cell:
                values[key] = cell[:2000]
        services.create_item(
            board,
            site.name or f"Site {site.line_number}",
            group=group.pk,
            values=values,
            actor=actor,
            ctx=ctx,
        )
    return board
