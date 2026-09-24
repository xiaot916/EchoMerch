from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

from app.core.local_database import BUSINESS_DAY, STORE_ID, LocalDatabase, q


class AlimamaReportIncomplete(RuntimeError):
    """Raised when a successful response is not complete enough to persist."""


def validate_campaign_buyer_metrics(
    pages: Iterable[Mapping[str, object]],
    business_day: date,
) -> None:
    """Reject the delayed snapshot where orders exist but buyer metrics are zero."""
    rows: list[Mapping[str, object]] = []
    total: Mapping[str, object] = {}
    for page in pages:
        data = page.get("data")
        if not isinstance(data, Mapping):
            continue
        page_rows = data.get("list")
        if isinstance(page_rows, list):
            rows.extend(item for item in page_rows if isinstance(item, Mapping))
        if not total:
            total_data = data.get("totalData")
            if isinstance(total_data, Mapping):
                total = total_data
            elif isinstance(total_data, list):
                total = next(
                    (item for item in total_data if isinstance(item, Mapping)),
                    {},
                )

    orders = _metric_total(total, rows, "alipayInshopNum")
    buyers = _metric_total(total, rows, "alipayInshopUv")
    buyer_field_count = sum("alipayInshopUv" in row for row in rows)
    if orders > 0 and (buyer_field_count == 0 or buyers <= 0):
        raise AlimamaReportIncomplete(
            f"{business_day.isoformat()} promotion snapshot is still settling: "
            f"orders={orders:g}, buyers={buyers:g}. Existing data was preserved."
        )


def preserve_existing_rows_on_empty_refresh(
    database: LocalDatabase,
    *,
    table: str,
    store_id: int,
    business_day: date,
    source_rows: int,
) -> None:
    """Do not let an anomalous empty refresh erase a non-empty business day."""
    if source_rows > 0:
        return
    with database.connect() as conn:
        row = conn.execute(
            f"select count(*) as row_count from {q(table)} "
            f"where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?",
            (store_id, business_day.isoformat()),
        ).fetchone()
    existing_rows = int(row["row_count"] or 0) if row else 0
    if existing_rows:
        raise AlimamaReportIncomplete(
            f"{business_day.isoformat()} returned no rows for {table}; "
            f"preserved {existing_rows} existing rows instead of replacing them."
        )


def _metric_total(
    total: Mapping[str, object],
    rows: Iterable[Mapping[str, object]],
    field: str,
) -> Decimal:
    if field in total:
        return _decimal(total.get(field))
    return sum((_decimal(row.get(field)) for row in rows), Decimal("0"))


def _decimal(value: object) -> Decimal:
    if value is None or isinstance(value, bool):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")
