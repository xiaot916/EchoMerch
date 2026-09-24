from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "alimama.cps.item_analysis_top_list"
PARSER_VERSION = "alimama-cps-items-v2"
MONEY_QUANTUM = Decimal("0.01")


class CpsItemsPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class CpsItemRow:
    item_id: str
    item_name: str
    item_price: Decimal | None
    item_url: str
    item_pic_url: str
    enter_shop_uv: Decimal | None
    enter_shop_pv: Decimal | None
    cart_items: Decimal | None
    favorite_items: Decimal | None
    payment_amount: Decimal | None
    payment_order_count: Decimal | None
    payment_buyer_count: Decimal | None
    estimated_commission: Decimal | None
    estimated_service_fee: Decimal | None
    estimated_total_fee: Decimal | None
    settled_commission: Decimal | None
    settled_service_fee: Decimal | None
    settled_total_fee: Decimal | None
    settled_amount: Decimal | None
    settled_order_count: Decimal | None
    settled_buyer_count: Decimal | None
    conversion_rate: Decimal | None

    @property
    def metric_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.enter_shop_uv,
                self.enter_shop_pv,
                self.cart_items,
                self.favorite_items,
                self.payment_amount,
                self.payment_order_count,
                self.payment_buyer_count,
                self.estimated_commission,
                self.estimated_service_fee,
                self.estimated_total_fee,
                self.settled_commission,
                self.settled_service_fee,
                self.settled_total_fee,
                self.settled_amount,
                self.settled_order_count,
                self.settled_buyer_count,
                self.conversion_rate,
            )
        )


@dataclass(frozen=True)
class ParsedCpsItems:
    platform_store_id: str
    business_day: date
    rows: list[CpsItemRow]
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
) -> ParsedCpsItems:
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
) -> ParsedCpsItems:
    pages = _pages(payload)
    rows: list[CpsItemRow] = []
    for page in pages:
        source_rows = _find_rows(page)
        if source_rows is None:
            raise CpsItemsPayloadError("The CPS item response has no row list.")
        rows.extend(_parse_row(row) for row in source_rows if isinstance(row, dict))
    if not rows:
        raise CpsItemsPayloadError("The CPS item response contains no item rows.")
    return ParsedCpsItems(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=rows,
        response_code=_response_code(payload),
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
    )


def _pages(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise CpsItemsPayloadError("The CPS item response must be a JSON object.")
    raw_pages = payload.get("pages")
    if isinstance(raw_pages, list):
        return [page for page in raw_pages if isinstance(page, dict)]
    return [payload]


def _parse_row(row: dict[str, Any]) -> CpsItemRow:
    item_id = _text(_first(row, "itemId", "item.id", "itemIdStr", "item_id", "id"))
    if not item_id:
        raise CpsItemsPayloadError("A CPS item row has no itemId.")
    return CpsItemRow(
        item_id=item_id,
        item_name=_text(_first(row, "itemName", "itemTitle", "title", "item.title")) or "",
        item_price=_money(_first(row, "itemPrice")),
        item_url=_text(_first(row, "itemUrl", "item.url")) or "",
        item_pic_url=_text(_first(row, "itemPicUrl", "picUrl")) or "",
        enter_shop_uv=_decimal(_first(row, "enterShopUvTk")),
        enter_shop_pv=_decimal(_first(row, "enterShopPvTk")),
        cart_items=_decimal(_first(row, "cartAddItmCnt")),
        favorite_items=_decimal(_first(row, "cltAddItmCnt")),
        payment_amount=_money(_first(row, "alipayAmt")),
        payment_order_count=_decimal(_first(row, "alipayNum", "alipayCnt")),
        payment_buyer_count=_decimal(_first(row, "alipayByrCnt")),
        estimated_commission=_money(_first(row, "preCommissionFee")),
        estimated_service_fee=_money(_first(row, "preServiceFee")),
        estimated_total_fee=_money(_first(row, "preTotalFee")),
        settled_commission=_money(_first(row, "cmCommissionFee")),
        settled_service_fee=_money(_first(row, "cmServiceFee")),
        settled_total_fee=_money(_first(row, "cmTotalFee")),
        settled_amount=_money(_first(row, "cpsSettleAmt", "tkSuccAmt")),
        settled_order_count=_decimal(_first(row, "cpsSettleNum", "tkSuccCnt")),
        settled_buyer_count=_decimal(_first(row, "tkSuccByrCnt", "cpsSettleByrCnt")),
        conversion_rate=_decimal(_first(row, "cvr")),
    )


def _find_rows(payload: dict[str, Any]) -> list[Any] | None:
    return _find_rows_in_value(payload, depth=0)


def _find_rows_in_value(value: Any, depth: int) -> list[Any] | None:
    if depth > 4:
        return None
    if isinstance(value, dict):
        for key in ("list", "data", "rows", "result", "items", "pageData"):
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


def _response_code(payload: dict[str, Any]) -> int:
    data = payload.get("data")
    for candidate in (
        payload.get("resultCode"),
        payload.get("code"),
        data.get("code") if isinstance(data, dict) else None,
    ):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return 0


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


def _money(value: Any) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
