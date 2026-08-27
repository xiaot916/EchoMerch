from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "sycm.mc.bybt.business_overview.statistics"
PARSER_VERSION = "sycm-bybt-v1"
MONEY_QUANTUM = Decimal("0.01")


class SycmBybtPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSycmBybt:
    platform_store_id: str
    business_day: date
    visitors: Decimal | None
    paid_buyers: Decimal | None
    online_items: Decimal | None
    paid_amount: Decimal | None
    paid_sub_order_count: Decimal | None
    paid_items: Decimal | None
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
                self.visitors,
                self.paid_buyers,
                self.online_items,
                self.paid_amount,
                self.paid_sub_order_count,
                self.paid_items,
            )
        )


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmBybt:
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
) -> ParsedSycmBybt:
    response_code = _as_int(payload.get("code"))
    if response_code != 0:
        message = payload.get("message") or payload.get("msg") or "unknown response error"
        raise SycmBybtPayloadError(f"SYCM BYBT response failed: {message}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise SycmBybtPayloadError("The SYCM BYBT response has no data object.")

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    parsed = ParsedSycmBybt(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        visitors=_metric_decimal(data, "bybtItemUv"),
        paid_buyers=_metric_decimal(data, "bybtPayByrCntNew"),
        online_items=_metric_decimal(data, "bybtOnlineItemCnt"),
        paid_amount=_money_metric(data, "bybtPayAmt"),
        paid_sub_order_count=_metric_decimal(data, "bybtPayOrdCntNew"),
        paid_items=_metric_decimal(data, "bybtPayOrdQty"),
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )
    required_metrics = {
        "百补访客": parsed.visitors,
        "百补支付买家": parsed.paid_buyers,
        "百补支付金额": parsed.paid_amount,
        "百补支付订单": parsed.paid_sub_order_count,
        "百补支付件数": parsed.paid_items,
    }
    missing = [label for label, value in required_metrics.items() if value is None]
    if missing:
        raise SycmBybtPayloadError(
            "百亿补贴接口未返回核心指标（"
            + "、".join(missing)
            + "）；请确认百亿补贴页面权限后重试。"
        )
    return parsed


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
