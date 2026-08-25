from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.warehouse.sycm_overview import ParsedMetric


METRIC_PREFIX = "customer."
DIMENSION_CODES = {"sellerId", "statDate"}


class SycmCustomerOverviewPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSycmCustomerOverview:
    platform_store_id: str
    business_day: date
    metrics: list[ParsedMetric]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str


def load_and_parse(path: Path, business_day: date) -> ParsedSycmCustomerOverview:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(payload, business_day=business_day, raw=raw)


def parse_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
) -> ParsedSycmCustomerOverview:
    response_code = _as_int(payload.get("code"))
    if response_code != 0:
        message = payload.get("message") or "unknown response error"
        raise SycmCustomerOverviewPayloadError(
            f"SYCM customer overview response failed: {message}"
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise SycmCustomerOverviewPayloadError(
            "The SYCM customer overview response has no data object."
        )

    platform_store_id = _value_as_text(data.get("sellerId"))
    if not platform_store_id:
        raise SycmCustomerOverviewPayloadError(
            "The SYCM customer overview response has no sellerId value."
        )

    index_desc = payload.get("extra", {}).get("indexDesc")
    if not isinstance(index_desc, dict):
        index_desc = {}

    metrics: list[ParsedMetric] = []
    for code, entry in data.items():
        if not isinstance(entry, dict) or not _is_self_metric_code(code):
            continue
        value_json = dict(entry)
        value_json["sourceCode"] = code
        desc = index_desc.get(code)
        if isinstance(desc, dict):
            value_json["label"] = desc.get("text")
            value_json["format"] = desc.get("format")
            value_json["explanation"] = desc.get("explanation")
        metrics.append(
            ParsedMetric(
                scope="self",
                code=f"{METRIC_PREFIX}{code}",
                numeric_value=_as_decimal(entry.get("value")),
                value_json=json.dumps(
                    value_json,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
            )
        )

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmCustomerOverview(
        platform_store_id=platform_store_id,
        business_day=business_day,
        metrics=metrics,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key="sycm.domain.one_query.customer_overview",
        parser_version="sycm-customer-overview-v1",
    )


def _is_self_metric_code(code: str) -> bool:
    if code in DIMENSION_CODES:
        return False
    lowered = code.lower()
    if "rival" in lowered:
        return False
    return not code.endswith("AvgGood")


def _value(entry: object) -> object:
    if isinstance(entry, dict):
        return entry.get("value")
    return None


def _value_as_text(entry: object) -> str:
    value = _value(entry)
    return "" if value is None else str(value)


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
