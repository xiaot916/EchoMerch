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
ENDPOINT_KEY = "sycm.s_content.brandnewdiscount.overview"
PARSER_VERSION = "sycm-new-customer-discount-v1"
MONEY_QUANTUM = Decimal("0.01")


class SycmNewCustomerDiscountPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSycmNewCustomerDiscount:
    platform_store_id: str
    business_day: date
    channel_id: str
    shop_visitors: Decimal | None
    product_new_visitors: Decimal | None
    new_customer_paid_buyers: Decimal | None
    new_customer_paid_buyer_ratio: Decimal | None
    new_customer_paid_amount: Decimal | None
    new_customer_paid_amount_ratio: Decimal | None
    new_customer_paid_conversion_rate: Decimal | None
    shop_new_customer_paid_buyers: Decimal | None
    shop_new_customer_paid_amount: Decimal | None
    shop_new_customer_paid_conversion_rate: Decimal | None
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
                self.shop_visitors,
                self.product_new_visitors,
                self.new_customer_paid_buyers,
                self.new_customer_paid_buyer_ratio,
                self.new_customer_paid_amount,
                self.new_customer_paid_amount_ratio,
                self.new_customer_paid_conversion_rate,
                self.shop_new_customer_paid_buyers,
                self.shop_new_customer_paid_amount,
                self.shop_new_customer_paid_conversion_rate,
            )
        )


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmNewCustomerDiscount:
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
) -> ParsedSycmNewCustomerDiscount:
    root = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    response_code = _as_int(root.get("code"))
    if response_code != 0:
        message = root.get("message") or root.get("msg") or "unknown response error"
        raise SycmNewCustomerDiscountPayloadError(
            f"SYCM new customer discount response failed: {message}"
        )

    data = root.get("data")
    if not isinstance(data, dict):
        raise SycmNewCustomerDiscountPayloadError(
            "The SYCM new customer discount response has no data object."
        )

    response_day = _entry_date(data.get("statDate"))
    if response_day is not None and response_day != business_day:
        raise SycmNewCustomerDiscountPayloadError(
            "The SYCM new customer discount response date does not match "
            f"the requested business day: {response_day} != {business_day}."
        )

    product_new_visitors = _metric_decimal(data, "guideNewUv")
    paid_buyers = _metric_decimal(data, "guideNewPayByrCnt")
    paid_amount = _money_metric(data, "guideNewPayAmt")
    conversion_rate = _metric_decimal(data, "guideNewPayRate")
    activity_complete = all(
        value is not None
        for value in (
            product_new_visitors,
            paid_buyers,
            paid_amount,
            conversion_rate,
        )
    )

    paid_buyer_ratio = _metric_decimal(data, "guideNewPayByrCntRatio")
    if paid_buyer_ratio is None:
        paid_buyer_ratio = _nested_decimal(data.get("guideNewPayByrCnt"), "ratio")

    paid_amount_ratio = _metric_decimal(data, "guideNewPayAmtRatio")
    if paid_amount_ratio is None:
        paid_amount_ratio = _nested_decimal(data.get("guideNewPayAmt"), "ratio")

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmNewCustomerDiscount(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        channel_id=_entry_text(data.get("channelId")),
        shop_visitors=_metric_decimal(data, "uv"),
        product_new_visitors=product_new_visitors if activity_complete else None,
        new_customer_paid_buyers=paid_buyers if activity_complete else None,
        new_customer_paid_buyer_ratio=paid_buyer_ratio if activity_complete else None,
        new_customer_paid_amount=paid_amount if activity_complete else None,
        new_customer_paid_amount_ratio=paid_amount_ratio if activity_complete else None,
        new_customer_paid_conversion_rate=conversion_rate if activity_complete else None,
        shop_new_customer_paid_buyers=_metric_decimal(data, "newbuyerPayByrCnt"),
        shop_new_customer_paid_amount=_money_metric(data, "newbuyerPayAmt"),
        shop_new_customer_paid_conversion_rate=_metric_decimal(
            data,
            "shopNewbuyerPayRate",
        ),
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


def _nested_decimal(entry: object, key: str) -> Decimal | None:
    if not isinstance(entry, dict):
        return None
    return _as_decimal(entry.get(key))


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
        text = str(entry).strip()
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    timestamp_ms = timestamp if timestamp >= 10**11 else timestamp * 1000
    try:
        return datetime.fromtimestamp(
            timestamp_ms / 1000,
            tz=CHINA_TIMEZONE,
        ).date()
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
