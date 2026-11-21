"""Bringing the price book in and out: Rapid's dump and CSV, and the CSV and PDF exports.

Staff use these from Django admin and `manage.py import_rapid_pricebook`. Rapid's CSV columns,
its "on Request only" prices, "Unrestricted" speeds and its export order are kept, so the files
staff already have still work.
"""

import csv
import io
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction

from .models import (
    PROVIDER_NAMES,
    PROVIDERS,
    VODACOM,
    AccessMedium,
    CatalogueProduct,
    ConnectProduct,
    PriceBook,
    PriceDefinition,
    SublayerProvider,
)

logger = logging.getLogger(__name__)

DEFAULT_BOOK = "Telejects"
POA = Decimal("-1.00")
LOGOS = Path(__file__).resolve().parent / "static" / "pricebook" / "logos"
SUBLAYER_LOGOS = {
    SublayerProvider.DFA: "dfa_logo.png",
    SublayerProvider.FROGFOOT: "frog_foot_logo.png",
    SublayerProvider.LINK_AFRICA: "la_logo.jpg",
    SublayerProvider.METRO_FIBRE: "mfm_logo.png",
    SublayerProvider.MTN: "mtn_logo.png",
    SublayerProvider.OCTOTEL: "octotel_logo.png",
    SublayerProvider.OPEN_FIBRE: "openfibre_logo.png",
    SublayerProvider.OPEN_SERVE: "open_serve_logo.png",
    SublayerProvider.THINKSPEED: "think_speed_logo.jpeg",
    SublayerProvider.VODACOM: "voda_logo.png",
    SublayerProvider.VUMATEL: "vuma_logo.png",
    SublayerProvider.WAN: "wan_logo.png",
}

# Rapid's template and import columns (ConnectProductDefinitionAdmin.csv_columns).
CSV_COLUMNS = [
    "provider_name (Vodacom, MTN, LINK_AFRICA)",
    "access_medium_id",
    "access_medium_name",
    "provider_product_name",
    "provider_product_id",
    "connect_name (Name of the product per Connect)",
    "monthly_recurring_cost (ZAR)",
    "none_recurring_cost (ZAR)",
    "duration (months)",
    "data_allocation (GB)",
    "data_allocation_notes",
    "max_bandwidth (Mbps)",
    "max_upload_bandwidth (Mbps)",
    "medium",
]

# Rapid's price book export (GeneratePricebookCSVView).
EXPORT_COLUMNS = [
    "Provider",
    "Product Name",
    "Access Medium",
    "Medium Type",
    "Download Speed (Mbps)",
    "Upload Speed (Mbps)",
    "Data Allocation (GB)",
    "Data Notes",
    "Contract Term (Months)",
    "Monthly Cost (ZAR)",
    "Setup Cost (ZAR)",
]


def default_book() -> PriceBook:
    book, _ = PriceBook.objects.get_or_create(name=DEFAULT_BOOK)
    return book


def _number(value) -> int | None:
    try:
        return int(str(value).strip())
    except TypeError, ValueError:
        return None


def _price(value: str, on_request: str) -> Decimal:
    """Rapid's: "MRC/NRC on Request only" (or POA) is -1; "R1,234.50" is 1234.50; else 0."""
    text = (value or "").strip()
    if text in (on_request, "POA"):
        return POA
    try:
        return Decimal(text.replace(",", "").replace("R", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


@dataclass
class ImportSummary:
    processed: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0

    def __str__(self):
        return (
            f"{self.processed} rows processed. Updated {self.updated} and created "
            f"{self.created}. {self.failed} row failures."
        )


def import_csv(text: str, book: PriceBook | None = None) -> ImportSummary:
    """Rapid's price definition CSV: one definition per row, made or updated, and added to the
    connect product named in it (made when new). A definition renamed into another connect
    product leaves its old one."""
    book = book or default_book()
    providers = {name: number for number, name in PROVIDERS}
    summary = ImportSummary()
    reader = csv.reader(io.StringIO(text))
    next(reader, None)  # the header
    for line, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        summary.processed += 1
        try:
            with transaction.atomic():
                created = _import_row(row, providers, book)
        except Exception as error:  # Rapid counted a bad row and went on
            logger.warning("Price book CSV line %s: %s", line, error)
            summary.failed += 1
            continue
        if created:
            summary.created += 1
        else:
            summary.updated += 1
    return summary


def _import_row(row: list[str], providers: dict, book: PriceBook) -> bool:
    provider = providers.get(_cell(row, 0))
    if provider is None:
        raise ValueError(f"Unknown provider {_cell(row, 0)!r}")
    product = CatalogueProduct.objects.filter(name=_cell(row, 3), provider=provider).first()
    access_medium = None
    if provider == VODACOM:
        access_medium = AccessMedium.objects.filter(name=_cell(row, 2)).order_by("id").first()
    if product is None and access_medium is None:
        raise ValueError("Neither a known access medium nor a known provider product")
    data_allocation = _number(_cell(row, 9))
    max_bandwidth = _number(_cell(row, 11))
    if max_bandwidth is None and "Unrestricted" in _cell(row, 11):
        max_bandwidth = 100  # Rapid's rule for unrestricted speeds
    max_upload = _number(_cell(row, 12))
    if max_upload is None:
        max_upload = max_bandwidth
    name = _cell(row, 5)
    if not name:
        raise ValueError("No connect name")
    duration = _number(_cell(row, 8))
    if duration is None:
        raise ValueError("No duration")
    connect_product = ConnectProduct.objects.filter(name=name).first()
    if connect_product is None:
        connect_product = ConnectProduct.objects.create(name=name, book=book)
    match = {
        "access_medium": access_medium,
        "product": product,
        "duration": duration,
        "data_allocation": data_allocation,
        "max_bandwidth": max_bandwidth,
        "max_upload_bandwidth": max_upload,
    }
    existing = PriceDefinition.objects.filter(**match).first()
    if existing is not None and existing.name != name:
        for old in existing.connect_products.exclude(pk=connect_product.pk):
            old.product_definitions.remove(existing)
    values = {
        "name": name,
        "provider": provider,
        "data_allocation_notes": _cell(row, 10),
        "monthly_recurring_cost": _price(_cell(row, 6), "MRC on Request only"),
        "none_recurring_cost": _price(_cell(row, 7), "NRC on Request only"),
        "medium": _cell(row, 13) or None,
    }
    if existing is None:
        definition = PriceDefinition.objects.create(**match, **values)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
        existing.save()
        definition = existing
    connect_product.product_definitions.add(definition)
    return existing is None


def template_csv() -> str:
    """Rapid's template: the columns, and a row per Vodacom access medium to fill in."""
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL)
    writer.writerow(CSV_COLUMNS)
    for medium in AccessMedium.objects.order_by("id"):
        writer.writerow(["Vodacom", medium.id, medium.name] + [""] * 10)
    return out.getvalue()


def _cost(value: Decimal) -> str:
    return "POA" if value == POA else f"{value:.2f}"


def _or_blank(value) -> str:
    return "" if value in (None, 0) else value


def export_csv(definitions=None) -> str:
    """Rapid's price book CSV: Vodacom first, by access medium; then the other providers.
    Every definition, or just `definitions` (what a company may see)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(EXPORT_COLUMNS)
    if definitions is None:
        definitions = PriceDefinition.objects.all()
    definitions = definitions.select_related("product", "access_medium")
    mediums = (
        AccessMedium.objects.filter(definitions__in=definitions.filter(provider=VODACOM))
        .distinct()
        .order_by("name")
    )
    for medium in mediums:
        rows = definitions.filter(access_medium=medium, provider=VODACOM).order_by(
            "max_bandwidth", "duration", "name"
        )
        for d in rows:
            writer.writerow(_export_row(d, "Vodacom", medium.name))
    for number, name in PROVIDERS[1:]:
        rows = definitions.filter(provider=number).order_by(
            "product__name", "max_bandwidth", "duration", "name"
        )
        for d in rows:
            writer.writerow(_export_row(d, name, ""))
    return out.getvalue()


def _export_row(d: PriceDefinition, provider: str, medium: str) -> list:
    return [
        provider,
        d.name,
        medium,
        d.medium or "",
        _or_blank(d.max_bandwidth),
        _or_blank(d.max_upload_bandwidth),
        _or_blank(d.data_allocation),
        d.data_allocation_notes or "",
        d.duration,
        _cost(d.monthly_recurring_cost),
        _cost(d.none_recurring_cost),
    ]


def export_pdf(definitions=None) -> bytes:
    """The price book as a PDF, landscape A4: a section per medium, then per sublayer (with its
    logo) and provider product, each a table of its definitions. Every definition, or just
    `definitions` (what a company may see)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.3 * inch,
        title="Telejects Price Book",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("BookTitle", parent=styles["Title"], fontSize=26)
    centred = ParagraphStyle("Centred", parent=styles["Normal"], alignment=TA_CENTER)
    section = ParagraphStyle("Section", parent=styles["Heading1"], fontSize=18)
    product_header = ParagraphStyle("Product", parent=styles["Heading3"])
    cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=9)

    elements = [
        Spacer(1, 1.2 * inch),
        Paragraph("Telejects Price Book", title),
        Spacer(1, 0.2 * inch),
        Paragraph(f"Effective date: {date.today():%d %B %Y}", centred),
        Spacer(1, 0.4 * inch),
        Paragraph(
            "<i>All prices are in ZAR and exclude VAT. Prices are subject to change.<br/>"
            "POA indicates price on application: please contact us for a quote.</i>",
            centred,
        ),
    ]
    by_medium: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    if definitions is None:
        definitions = PriceDefinition.objects.all()
    definitions = definitions.select_related("product", "access_medium").order_by(
        "medium", "sublayer", "max_bandwidth", "name", "id"
    )
    for d in definitions:
        by_medium[d.medium or "Other"][d.sublayer].append(d)
    for medium in sorted(by_medium):
        elements += [PageBreak(), Paragraph(f"{medium} products", section), Spacer(1, 0.2 * inch)]
        sublayers = by_medium[medium]
        for sublayer in sorted(sublayers, key=lambda s: (s is None, s)):
            logo = LOGOS / SUBLAYER_LOGOS.get(sublayer, "") if sublayer is not None else None
            if logo is not None and logo.is_file():
                image = Image(str(logo), width=0.75 * inch, height=0.75 * inch, kind="proportional")
                image.hAlign = "LEFT"
                elements.append(image)
            elif sublayer is not None:
                elements.append(Paragraph(SublayerProvider(sublayer).label, product_header))
            by_product: dict = defaultdict(list)
            for d in sublayers[sublayer]:
                by_product[
                    (d.provider, d.product.name if d.product else d.access_medium.name)
                ].append(d)
            for (provider, name), rows in sorted(by_product.items()):
                elements.append(Paragraph(f"{name} ({PROVIDER_NAMES[provider]})", product_header))
                elements.append(_pdf_table(rows, cell, Table, TableStyle, colors, inch, Paragraph))
                elements.append(Spacer(1, 0.3 * inch))
    doc.build(elements)
    return buffer.getvalue()


def _pdf_table(rows, cell, Table, TableStyle, colors, inch, Paragraph):  # noqa: N803
    head = [
        "Name",
        "Speed (Mbps)",
        "Upload (Mbps)",
        "Data (GB)",
        "Term (months)",
        "Monthly",
        "Setup",
    ]
    data = [[Paragraph(f"<b>{h}</b>", cell) for h in head]]
    for d in rows:
        data_cell = d.data_allocation_notes or (
            str(d.data_allocation) if d.data_allocation else "-"
        )
        data.append(
            [
                Paragraph(d.name, cell),
                Paragraph(str(d.max_bandwidth or "-"), cell),
                Paragraph(str(d.max_upload_bandwidth or "-"), cell),
                Paragraph(data_cell, cell),
                Paragraph(str(d.duration), cell),
                Paragraph(
                    "POA"
                    if d.monthly_recurring_cost == POA
                    else f"R {d.monthly_recurring_cost:,.2f}",
                    cell,
                ),
                Paragraph(
                    "POA" if d.none_recurring_cost == POA else f"R {d.none_recurring_cost:,.2f}",
                    cell,
                ),
            ]
        )
    widths = [3.6 * inch, 1.1 * inch, 1.1 * inch, 1.5 * inch, 1.1 * inch, 1.3 * inch, 1.3 * inch]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


# --- Rapid's dump ----------------------------------------------------------------------------

RAPID_MODELS = {
    "connect.product": "products",
    "connect.accessmedium": "mediums",
    "connect.connectproductdefinition": "definitions",
    "connect.connectproduct": "connect_products",
}


def _product_code(provider: int, fields: dict) -> str:
    """Vodacom's products are numbered; the rest are named (as each connector syncs them)."""
    if provider == VODACOM and fields.get("product_id") is not None:
        return str(fields["product_id"])
    return fields["name"]


@transaction.atomic
def import_rapid_dump(text: str, book: PriceBook | None = None) -> dict[str, int]:
    """Rapid's price book, from `manage.py dumpdata connect.Product connect.AccessMedium
    connect.ConnectProductDefinition connect.ConnectProduct` on Rapid, with every id kept.

    Running it again updates the same rows: nothing is duplicated."""
    book = book or default_book()
    rows: dict[str, list] = {name: [] for name in RAPID_MODELS.values()}
    for item in json.loads(text):
        name = RAPID_MODELS.get(item.get("model", "").lower())
        if name:
            rows[name].append(item)
    for item in rows["products"]:
        f = item["fields"]
        CatalogueProduct.objects.update_or_create(
            pk=item["pk"],
            defaults={
                "product_id": f.get("product_id"),
                "name": f["name"],
                "provider": f["provider"],
                "product_code": _product_code(f["provider"], f),
            },
        )
    for item in rows["mediums"]:
        f = item["fields"]
        AccessMedium.objects.update_or_create(
            pk=item["pk"],
            defaults={
                "provider_access_medium_identifier_id": f["provider_access_medium_identifier_id"],
                "name": f["name"],
            },
        )
    for item in rows["definitions"]:
        f = item["fields"]
        PriceDefinition.objects.update_or_create(
            pk=item["pk"],
            defaults={
                "name": f["name"],
                "access_medium_id": f.get("access_medium"),
                "product_id": f.get("product"),
                "provider": f.get("provider", VODACOM),
                "sublayer": f.get("sublayer"),
                "duration": f.get("duration", 12),
                "monthly_recurring_cost": Decimal(str(f["monthly_recurring_cost"])),
                "none_recurring_cost": Decimal(str(f["none_recurring_cost"])),
                "data_allocation": f.get("data_allocation"),
                "data_allocation_notes": f.get("data_allocation_notes"),
                "max_bandwidth": f.get("max_bandwidth"),
                "max_upload_bandwidth": f.get("max_upload_bandwidth"),
                "medium": f.get("medium"),
            },
        )
    for item in rows["connect_products"]:
        f = item["fields"]
        connect_product, _ = ConnectProduct.objects.update_or_create(
            pk=item["pk"],
            defaults={"name": f["name"], "description": f.get("description"), "book": book},
        )
        connect_product.product_definitions.set(f.get("product_definitions", []))
    reset_sequences()
    return {name: len(items) for name, items in rows.items()}


def reset_sequences() -> None:
    """Ids were given, so start Postgres' sequences after the highest one."""
    from django.core.management.color import no_style
    from django.db import connection

    models = [CatalogueProduct, AccessMedium, PriceDefinition, ConnectProduct]
    statements = connection.ops.sequence_reset_sql(no_style(), models)
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)
