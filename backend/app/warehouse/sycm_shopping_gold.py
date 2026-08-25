from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


CHINA_TIMEZONE = timezone(timedelta(hours=8))
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "sycm.xsite.rc.get_rc_overall"
PARSER_VERSION = "sycm-shopping-gold-v1"
MONEY_QUANTUM = Decimal("0.01")


class SycmShoppingGoldPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSycmShoppingGold:
    platform_store_id: str
    business_day: date
    average_recharge_amount: Decimal | None
    recharge_amount: Decimal | None
    paid_buyers: Decimal | None
    recharge_items: Decimal | None
    recharge_refund_amount: Decimal | None
    paid_amount: Decimal | None
    customer_unit_price: Decimal | None
    recharge_capital_amount: Decimal | None
    recharge_buyers: Decimal | None
    recharge_rate: Decimal | None
    product_visitors: Decimal | None
    recharge_sub_order_count: Decimal | None
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str

    @property
    def metric_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.average_recharge_amount,
                self.recharge_amount,
                self.paid_buyers,
                self.recharge_items,
                self.recharge_refund_amount,
                self.paid_amount,
                self.customer_unit_price,
                self.recharge_capital_amount,
                self.recharge_buyers,
                self.recharge_rate,
                self.product_visitors,
                self.recharge_sub_order_count,
            )
        )


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmShoppingGold:
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
) -> ParsedSycmShoppingGold:
    root = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    response_code = _as_int(root.get("code"))
    if response_code != 0:
        message = root.get("message") or root.get("msg") or "unknown response error"
        raise SycmShoppingGoldPayloadError(f"SYCM shopping gold response failed: {message}")

    data = root.get("data")
    if not isinstance(data, dict):
        raise SycmShoppingGoldPayloadError("The SYCM shopping gold response has no data object.")

    response_day = _entry_date(data.get("statDate"))
    if response_day is not None and response_day != business_day:
        raise SycmShoppingGoldPayloadError(
            f"The response date does not match the requested day: {response_day} != {business_day}."
        )

    platform_store_id = _entry_text(data.get("userId")) or fallback_platform_store_id
    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmShoppingGold(
        platform_store_id=platform_store_id,
        business_day=business_day,
        average_recharge_amount=_money_metric(data, "avgRcAmt"),
        recharge_amount=_money_metric(data, "rcAmt"),
        paid_buyers=_metric_decimal(data, "rcPayByrCnt"),
        recharge_items=_metric_decimal(data, "rechargeItemCnt"),
        recharge_refund_amount=_money_metric(data, "rechargeSucRfdAmt"),
        paid_amount=_money_metric(data, "rcPayAmt"),
        customer_unit_price=_money_metric(data, "rcPayOrdPbt"),
        recharge_capital_amount=_money_metric(data, "rcCapitalAmt"),
        recharge_buyers=_metric_decimal(data, "rcByrCnt"),
        recharge_rate=_metric_decimal(data, "rcRate"),
        product_visitors=_metric_decimal(data, "itmUv"),
        recharge_sub_order_count=_metric_decimal(data, "rechargeOrdCnt"),
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _metric_decimal(data: dict[str, Any], code: str) -> Decimal | None:
    entry = data.get(code)
    if isinstance(entry, dict):
        return _as_decimal(entry.get("value"))
    return _as_decimal(entry)


def _money_metric(data: dict[str, Any], code: str) -> Decimal | None:
    value = _metric_decimal(data, code)
    if value is None:
        return None
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _entry_text(entry: object) -> str:
    if isinstance(entry, dict):
        entry = entry.get("value")
    return "" if entry is None else str(entry)


def _entry_date(entry: object) -> date | None:
    if isinstance(entry, dict):
        entry = entry.get("value")
    if entry is None or isinstance(entry, bool):
        return None
    try:
        timestamp = int(entry)
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(str(entry)[:10])
        except ValueError:
            return None
    timestamp_ms = timestamp if timestamp >= 10**11 else timestamp * 1000
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=CHINA_TIMEZONE).date()
    except (OverflowError, OSError, ValueError):
        return None


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
