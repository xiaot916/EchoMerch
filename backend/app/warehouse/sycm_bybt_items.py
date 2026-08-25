from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "sycm.mc.bybt.item_list"
PARSER_VERSION = "sycm-bybt-items-v1"
MONEY_QUANTUM = Decimal("0.01")


class SycmBybtItemsPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class BybtItemRow:
    item_id: str
    marketing_id: str
    item_name: str
    category_name: str
    business_scenario: str
    sales_method: str
    race_type: str
    play_type: str
    paid_amount: Decimal | None
    paid_items: Decimal | None
    paid_sub_order_count: Decimal | None
    visitors: Decimal | None
    conversion_rate: Decimal | None

    @property
    def metric_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.paid_amount,
                self.paid_items,
                self.paid_sub_order_count,
                self.visitors,
                self.conversion_rate,
            )
        )


@dataclass(frozen=True)
class ParsedSycmBybtItems:
    platform_store_id: str
    business_day: date
    rows: list[BybtItemRow]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return sum(row.metric_count for row in self.rows)


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmBybtItems:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(
        payload,
        business_day=business_day,
        raw=raw,
        fallback_platform_store_id=fallback_platform_store_id,
    )


def parse_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmBybtItems:
    pages = _pages(payload)
    rows: list[BybtItemRow] = []
    for page in pages:
        code = _as_int(page.get("code"))
        if code != 0:
            message = page.get("message") or page.get("msg") or "unknown response error"
            raise SycmBybtItemsPayloadError(f"SYCM BYBT item response failed: {message}")
        source_rows = _find_rows(page)
        if source_rows is None:
            raise SycmBybtItemsPayloadError("The SYCM BYBT item response has no row list.")
        rows.extend(_parse_row(row) for row in source_rows if isinstance(row, dict))

    return ParsedSycmBybtItems(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=rows,
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
    )


def _pages(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise SycmBybtItemsPayloadError("The SYCM BYBT item response must be a JSON object.")
    raw_pages = payload.get("pages")
    if isinstance(raw_pages, list):
        return [page for page in raw_pages if isinstance(page, dict)]
    return [payload]


def _parse_row(row: dict[str, Any]) -> BybtItemRow:
    item_id = _text(_first(row, "itemId", "item.id", "item.itemId", "item_id"))
    if not item_id:
        raise SycmBybtItemsPayloadError("A SYCM BYBT item row has no itemId.")
    paid_amount = _decimal(_first(row, "bybtPayAmt", "payAmt"))
    if paid_amount is not None:
        paid_amount = paid_amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return BybtItemRow(
        item_id=item_id,
        marketing_id=_text(_first(row, "juId", "activityId", "marketingId", "campaignId")) or "",
        item_name=_text(_first(row, "item.title", "itemName", "itemTitle", "title")) or "",
        category_name=_text(_first(row, "bybtCateFullName", "cateFullName", "categoryName")) or "",
        business_scenario=_text(_first(row, "businessScenario")) or "",
        sales_method=_text(_first(row, "salesMethod")) or "",
        race_type=_text(_first(row, "raceType")) or "",
        play_type=_text(_first(row, "playType")) or "",
        paid_amount=paid_amount,
        paid_items=_decimal(_first(row, "bybtPayOrdQty", "payOrdQty")),
        paid_sub_order_count=_decimal(_first(row, "bybtPayOrdCntNew", "payOrdCnt")),
        visitors=_decimal(_first(row, "bybtItemUv", "itemUv", "uv")),
        conversion_rate=_decimal(_first(row, "bybtCvr", "cvr", "payRate")),
    )


def _find_rows(payload: dict[str, Any]) -> list[Any] | None:
    return _find_rows_in_value(payload, depth=0)


def _find_rows_in_value(value: Any, depth: int) -> list[Any] | None:
    if depth > 4:
        return None
    if isinstance(value, dict):
        for key in ("data", "list", "pageData", "rows", "result", "items"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate
        for key in ("data", "result", "content"):
            candidate = value.get(key)
            if isinstance(candidate, dict):
                found = _find_rows_in_value(candidate, depth + 1)
                if found is not None:
                    return found
    return None


def _first(row: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = row
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value is not None:
            while isinstance(value, dict) and "value" in value:
                value = value["value"]
            return value
    return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
