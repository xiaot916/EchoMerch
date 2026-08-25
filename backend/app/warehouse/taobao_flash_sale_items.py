from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "taobao.sale.tbhj_item_data_query"
PARSER_VERSION = "taobao-flash-sale-items-v1"
MONEY_QUANTUM = Decimal("0.01")


class TaobaoFlashSaleItemsPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class TaobaoFlashSaleItemRow:
    item_id: str
    activity_id: str
    item_name: str
    activity_name: str
    activity_status: str
    activity_start_time: str
    activity_end_time: str
    ipv: Decimal | None
    ipv_uv: Decimal | None
    paid_order_count: Decimal | None
    paid_amount: Decimal | None
    new_customers: Decimal | None
    conversion_rate: Decimal | None

    @property
    def metric_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.ipv, self.ipv_uv, self.paid_order_count, self.paid_amount,
                self.new_customers, self.conversion_rate,
            )
        )


@dataclass(frozen=True)
class ParsedTaobaoFlashSaleItems:
    platform_store_id: str
    business_day: date
    rows: list[TaobaoFlashSaleItemRow]
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
) -> ParsedTaobaoFlashSaleItems:
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
) -> ParsedTaobaoFlashSaleItems:
    pages = _pages(payload)
    rows: list[TaobaoFlashSaleItemRow] = []
    for page in pages:
        if page.get("success") is False:
            message = page.get("message") or page.get("msg") or "unknown response error"
            raise TaobaoFlashSaleItemsPayloadError(f"Taobao flash-sale item response failed: {message}")
        source_rows = _find_rows(page)
        if source_rows is None:
            raise TaobaoFlashSaleItemsPayloadError("The Taobao flash-sale item response has no row list.")
        rows.extend(_parse_row(row) for row in source_rows if isinstance(row, dict))
    return ParsedTaobaoFlashSaleItems(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=rows,
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
    )


def _pages(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise TaobaoFlashSaleItemsPayloadError("The Taobao flash-sale item response must be a JSON object.")
    raw_pages = payload.get("pages")
    if isinstance(raw_pages, list):
        return [page for page in raw_pages if isinstance(page, dict)]
    return [payload]


def _parse_row(row: dict[str, Any]) -> TaobaoFlashSaleItemRow:
    item_id = _text(_first(row, "itemId", "item.id", "item.itemId", "auctionId", "numIid"))
    if not item_id:
        raise TaobaoFlashSaleItemsPayloadError("A Taobao flash-sale item row has no itemId.")
    paid_amount = _decimal(_first(row, "payOrderAmt", "payOrdAmt", "payAmt", "paidAmount"))
    if paid_amount is not None:
        paid_amount = paid_amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return TaobaoFlashSaleItemRow(
        item_id=item_id,
        activity_id=_text(_first(row, "activityId", "juId", "campaignId", "actId")) or "",
        item_name=_text(_first(row, "item.title", "itemName", "itemTitle", "title")) or "",
        activity_name=_text(_first(row, "activityName", "actName", "campaignName")) or "",
        activity_status=_text(_first(row, "activityStatus", "status")) or "",
        activity_start_time=_text(_first(row, "activityStartTime", "startTime", "actStartTime")) or "",
        activity_end_time=_text(_first(row, "activityEndTime", "endTime", "actEndTime")) or "",
        ipv=_decimal(_first(row, "ipv", "itemIpv", "pv")),
        ipv_uv=_decimal(_first(row, "ipvUv", "itemIpvUv", "uv")),
        paid_order_count=_decimal(_first(row, "payOrderCnt", "payOrdCnt", "paidOrderCount")),
        paid_amount=paid_amount,
        new_customers=_decimal(_first(row, "newDac", "newCustomerCnt", "newPayByrCnt")),
        conversion_rate=_decimal(_first(row, "payOrderCvr", "payOrdCntRate", "cvr", "payRate")),
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
