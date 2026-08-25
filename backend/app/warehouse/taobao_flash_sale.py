from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "taobao.sale.tbhj_activity_data_query"
PARSER_VERSION = "taobao-flash-sale-v1"
MONEY_QUANTUM = Decimal("0.01")

FLASH_SALE_METRIC_CODES = (
    "itemCnt",
    "ipv",
    "ipvUv",
    "payOrderCnt",
    "payOrderAmt",
    "newDac",
    "payOrderCntCoef",
)
MONEY_CODES = {"payOrderAmt"}


class TaobaoFlashSalePayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTaobaoFlashSale:
    platform_store_id: str
    business_day: date
    metrics: dict[str, Decimal | None]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str

    @property
    def metric_count(self) -> int:
        return sum(value is not None for value in self.metrics.values())


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedTaobaoFlashSale:
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
) -> ParsedTaobaoFlashSale:
    if payload.get("success") is False:
        message = payload.get("message") or payload.get("msg") or "unknown response error"
        raise TaobaoFlashSalePayloadError(f"Taobao flash sale response failed: {message}")

    data_root = payload.get("data")
    rows = data_root.get("data") if isinstance(data_root, dict) else None
    if not isinstance(rows, list):
        raise TaobaoFlashSalePayloadError(
            "The Taobao flash sale response has no data.data list."
        )

    metrics = {code: None for code in FLASH_SALE_METRIC_CODES}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("type") or "").strip()
        if code not in metrics:
            continue
        value = _detail_value_for_day(row, business_day)
        if value is None:
            value = row.get("value")
        decimal_value = _as_decimal(value)
        if decimal_value is not None and code in MONEY_CODES:
            decimal_value = decimal_value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        metrics[code] = decimal_value

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedTaobaoFlashSale(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        metrics=metrics,
        response_code=0,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _detail_value_for_day(row: dict[str, Any], business_day: date) -> object | None:
    details = row.get("detailList")
    if not isinstance(details, list):
        return None
    for detail in details:
        if not isinstance(detail, dict):
            continue
        if _parse_day(detail.get("ds")) == business_day:
            return detail.get("value")
    return None


def _parse_day(value: object) -> date | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
