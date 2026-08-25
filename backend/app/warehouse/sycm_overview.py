from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


CHINA_TIMEZONE = timezone(timedelta(hours=8))


class SycmOverviewPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedMetric:
    scope: str
    code: str
    numeric_value: Decimal | None
    value_json: str


@dataclass(frozen=True)
class ParsedSycmOverview:
    platform_store_id: str
    business_day: date
    metrics: list[ParsedMetric]
    canonical: dict[str, Decimal | int]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str


def load_and_parse(path: Path, business_day: date) -> ParsedSycmOverview:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(payload, business_day=business_day, raw=raw)


def parse_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
) -> ParsedSycmOverview:
    content = payload.get("content")
    if not isinstance(content, dict):
        raise SycmOverviewPayloadError("The SYCM overview response has no content object.")

    response_code = _as_int(content.get("code"))
    if response_code != 0:
        message = content.get("message") or "unknown response error"
        raise SycmOverviewPayloadError(f"SYCM overview response failed: {message}")

    data = content.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("self"), dict):
        raise SycmOverviewPayloadError("The SYCM overview response has no self metric group.")

    self_group = data["self"]
    if _is_trend_group(self_group):
        self_group = _extract_trend_business_day(self_group, business_day)
        endpoint_key = "sycm.portal.core_index.trend.v3"
        parser_version = "sycm-overview-v2"
    else:
        endpoint_key = "sycm.portal.core_index.overview.v3"
        parser_version = "sycm-overview-v2"

    platform_store_id = _value_as_text(self_group.get("userId"))
    if not platform_store_id:
        raise SycmOverviewPayloadError("The SYCM overview response has no self.userId value.")

    metrics: list[ParsedMetric] = []
    for code, entry in self_group.items():
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        metrics.append(
            ParsedMetric(
                scope="self",
                code=code,
                numeric_value=_as_decimal(value),
                value_json=json.dumps(
                    entry,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
            )
        )

    canonical = {
        "paid_amount": _as_decimal_or_zero(_value(self_group.get("payAmt"))),
        "visitors": _as_int(_value(self_group.get("uv"))),
        "buyers": _as_int(_value(self_group.get("payByrCnt"))),
        "conversion_rate": _as_decimal_or_zero(_value(self_group.get("payRate"))),
        "promotion_cost": _as_decimal_or_zero(_value(self_group.get("admCostFamtQzt"))),
        "paid_orders": _as_int(_value(self_group.get("payOrdCnt"))),
        "paid_items": _as_int(_value(self_group.get("payItmCnt"))),
        "page_views": _as_int(_value(self_group.get("pv"))),
        "cart_count": _as_int(_value(self_group.get("cartCnt"))),
        "cart_buyers": _as_int(_value(self_group.get("cartByrCnt"))),
        "p4p_spend": _as_decimal_or_zero(_value(self_group.get("p4pExpendAmt"))),
        "taoke_spend": _as_decimal_or_zero(_value(self_group.get("tkExpendAmt"))),
    }

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmOverview(
        platform_store_id=platform_store_id,
        business_day=business_day,
        metrics=metrics,
        canonical=canonical,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=endpoint_key,
        parser_version=parser_version,
    )


def _is_trend_group(self_group: dict[str, Any]) -> bool:
    return isinstance(self_group.get("statDate"), list)


def _extract_trend_business_day(
    self_group: dict[str, Any],
    business_day: date,
) -> dict[str, dict[str, Any]]:
    stat_dates = self_group.get("statDate")
    if not isinstance(stat_dates, list):
        raise SycmOverviewPayloadError("The SYCM trend response has no statDate series.")

    target_index = None
    available_days: list[str] = []
    for index, raw_day in enumerate(stat_dates):
        parsed_day = _stat_date_to_business_day(raw_day)
        if parsed_day is None:
            continue
        available_days.append(parsed_day.isoformat())
        if parsed_day == business_day:
            target_index = index

    if target_index is None:
        sample_days = ", ".join(available_days[:3] + available_days[-3:])
        raise SycmOverviewPayloadError(
            f"The SYCM trend response does not contain {business_day.isoformat()}; "
            f"available sample days: {sample_days}"
        )

    extracted: dict[str, dict[str, Any]] = {}
    for code, series in self_group.items():
        if not isinstance(series, list):
            continue
        value = series[target_index] if target_index < len(series) else None
        extracted[code] = {
            "value": value,
            "sourceDate": business_day.isoformat(),
            "sourceIndex": target_index,
        }
    return extracted


def _stat_date_to_business_day(value: object) -> date | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=CHINA_TIMEZONE).date()


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


def _as_decimal_or_zero(value: object) -> Decimal:
    return _as_decimal(value) or Decimal("0")


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
