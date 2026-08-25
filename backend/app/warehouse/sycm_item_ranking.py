from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.local_database import (
    PRODUCT_RANKING_FIELDS,
    PRODUCT_RANKING_ITEM_ID,
    PRODUCT_RANKING_ITEM_NAME,
    PRODUCT_RANKING_ITEM_STATUS,
)


ITEM_RANKING_ENDPOINT = "sycm.cc.item.view.top"
PARSER_VERSION = "sycm-item-ranking-v1"


class SycmItemRankingPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedItemRanking:
    business_day: date
    rows: list[dict[str, str | None]]
    reached_zero_payment_items: bool
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ITEM_RANKING_ENDPOINT
    parser_version: str = PARSER_VERSION


def load_and_parse(path: Path, business_day: date) -> ParsedItemRanking:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(payload, business_day=business_day, raw=raw)


def parse_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
) -> ParsedItemRanking:
    if not isinstance(payload, dict):
        raise SycmItemRankingPayloadError("The item ranking response must be a JSON object.")

    if isinstance(payload.get("pages"), list):
        page_payloads = [page for page in payload["pages"] if isinstance(page, dict)]
    else:
        page_payloads = [payload]

    rows: list[dict[str, str | None]] = []
    response_codes: list[int] = []
    reached_zero_payment_items = False
    for page_payload in page_payloads:
        response_code = _response_code(page_payload)
        if response_code is not None:
            response_codes.append(response_code)
        page_rows = _find_rows(page_payload)
        if page_rows is None:
            raise SycmItemRankingPayloadError(
                "The item ranking response has no data.data row list."
            )
        parsed_page_rows = [_parse_row(row) for row in page_rows if isinstance(row, dict)]
        positive_rows, reached_zero = split_rows_at_zero_payment_items(parsed_page_rows)
        rows.extend(positive_rows)
        if reached_zero:
            reached_zero_payment_items = True
            break

    if response_codes and any(code != 0 for code in response_codes):
        raise SycmItemRankingPayloadError(
            f"SYCM item ranking response failed with code {response_codes[0]}."
        )
    if not response_codes:
        raise SycmItemRankingPayloadError("The item ranking response has no response code.")

    return ParsedItemRanking(
        business_day=business_day,
        rows=rows,
        reached_zero_payment_items=reached_zero_payment_items,
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
    )


def split_rows_at_zero_payment_items(
    rows: list[dict[str, str | None]],
) -> tuple[list[dict[str, str | None]], bool]:
    """Keep ranked rows until the first row whose payment item count is zero."""
    positive_rows: list[dict[str, str | None]] = []
    reached_zero = False
    for row in rows:
        count = _as_decimal(row.get("支付件数"))
        if count is not None and count <= 0:
            reached_zero = True
            break
        positive_rows.append(row)
    return positive_rows, reached_zero


def payment_item_count(row: dict[str, str | None]) -> Decimal | None:
    return _as_decimal(row.get("支付件数"))


def _parse_row(row: dict[str, Any]) -> dict[str, str | None]:
    item_id = _as_text(_first_value(row, ("itemId.value", "itemId")))
    if not item_id:
        raise SycmItemRankingPayloadError("A product ranking row has no itemId.")

    parsed: dict[str, str | None] = {
        PRODUCT_RANKING_ITEM_ID: item_id,
        PRODUCT_RANKING_ITEM_NAME: _as_text(_first_value(row, ("item.title", "itemName"))) or "",
    }
    for column, code in PRODUCT_RANKING_FIELDS:
        if column == PRODUCT_RANKING_ITEM_STATUS:
            parsed[column] = _as_text(_first_value(row, (code, f"{code}.value"))) or ""
            continue
        aliases = _FIELD_ALIASES.get(code, (f"{code}.value", code))
        parsed[column] = _as_text(_first_value(row, aliases))
    return parsed


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "itemCartCnt": ("itemCartCnt.value", "crtItmQty.value", "itemCartCnt"),
    "itmStayTime": ("itmStayTime.value", "stayTimeAvg.value", "itmStayTime"),
}


def _find_rows(payload: dict[str, Any]) -> list[Any] | None:
    return _find_rows_in_value(payload, depth=0)


def _find_rows_in_value(value: Any, depth: int) -> list[Any] | None:
    if depth > 4:
        return None
    if isinstance(value, dict):
        candidate = value.get("data")
        if isinstance(candidate, list):
            return candidate
        for key in ("content", "data", "result"):
            if key in value:
                found = _find_rows_in_value(value[key], depth + 1)
                if found is not None:
                    return found
    return None


def _response_code(payload: dict[str, Any]) -> int | None:
    for value in (payload, payload.get("content"), payload.get("data")):
        if isinstance(value, dict) and value.get("code") is not None:
            return _as_int(value.get("code"))
    return None


def _first_value(row: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = row
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value is not None:
            if isinstance(value, dict) and "value" in value:
                value = value["value"]
            return value
    return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
