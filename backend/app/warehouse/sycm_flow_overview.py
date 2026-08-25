from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.warehouse.sycm_overview import ParsedMetric


METRIC_PREFIX = "flow."


class SycmFlowOverviewPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSycmFlowOverview:
    business_day: date
    metrics: list[ParsedMetric]
    canonical: dict[str, Decimal | int]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str


def load_and_parse(path: Path, business_day: date) -> ParsedSycmFlowOverview:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(payload, business_day=business_day, raw=raw)


def parse_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
) -> ParsedSycmFlowOverview:
    root = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    response_code = _as_int(root.get("code"))
    if response_code != 0:
        message = root.get("message") or payload.get("message") or "unknown response error"
        raise SycmFlowOverviewPayloadError(f"SYCM flow overview response failed: {message}")

    data = root.get("data")
    if not isinstance(data, dict):
        raise SycmFlowOverviewPayloadError("The SYCM flow overview response has no data object.")

    metric_group = data.get("data")
    if not isinstance(metric_group, dict):
        raise SycmFlowOverviewPayloadError(
            "The SYCM flow overview response has no data.data metric group."
        )

    metrics: list[ParsedMetric] = []
    for code, entry in metric_group.items():
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        value_json = dict(entry)
        value_json["sourceCode"] = code
        metrics.append(
            ParsedMetric(
                scope="self",
                code=f"{METRIC_PREFIX}{code}",
                numeric_value=_as_decimal(value),
                value_json=json.dumps(
                    value_json,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
            )
        )

    canonical = {
        "paid_amount": _as_decimal_or_zero(_value(metric_group.get("payAmt"))),
        "visitors": _as_int(_value(metric_group.get("uv"))),
        "buyers": _as_int(_value(metric_group.get("payByrCnt"))),
        "conversion_rate": _as_decimal_or_zero(_value(metric_group.get("payRate"))),
        "promotion_cost": Decimal("0"),
        "paid_orders": 0,
        "paid_items": 0,
        "page_views": _as_int(_value(metric_group.get("pv"))),
        "cart_count": 0,
        "cart_buyers": _as_int(_value(metric_group.get("cartByrCnt"))),
        "p4p_spend": Decimal("0"),
        "taoke_spend": Decimal("0"),
    }

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmFlowOverview(
        business_day=business_day,
        metrics=metrics,
        canonical=canonical,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key="sycm.flow.new.guide.trend.overview",
        parser_version="sycm-flow-overview-v1",
    )


def _value(entry: object) -> object:
    if isinstance(entry, dict):
        return entry.get("value")
    return None


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _as_decimal_or_zero(value: object) -> Decimal:
    return _as_decimal(value) or Decimal("0")


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
