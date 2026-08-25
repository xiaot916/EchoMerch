from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.warehouse.sycm_overview import ParsedMetric


SECTION_PREFIXES = {
    "core": "member.core.",
    "asset": "member.asset.",
    "repurchase": "member.repurchase.",
    "acquisition": "member.acquisition.",
}

SECTION_ENDPOINT_KEYS = {
    "core": "sycm.domain.one_query.member_core",
    "asset": "sycm.domain.one_query.member_asset",
    "repurchase": "sycm.domain.one_query.member_repurchase",
    "acquisition": "sycm.domain.one_query.member_acquisition",
}

DIMENSION_CODES = {
    "sellerId",
    "statDate",
    "channelGroupName",
    "channelGroupLink",
}


class SycmMemberAnalysisPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSycmMemberMetrics:
    platform_store_id: str
    business_day: date
    section: str
    metrics: list[ParsedMetric]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str


@dataclass(frozen=True)
class ParsedMemberChannelRow:
    row_order: int
    channel_name: str
    channel_link: str
    new_members: Decimal
    paid_new_members: Decimal
    recruit_conversion_rate: Decimal
    new_member_paid_amount: Decimal
    new_member_unit_price: Decimal
    value_json: str


@dataclass(frozen=True)
class ParsedSycmMemberChannel:
    platform_store_id: str
    business_day: date
    rows: list[ParsedMemberChannelRow]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str


def load_and_parse_metrics(
    path: Path,
    business_day: date,
    section: str,
    platform_store_id: str = "2200573698992",
) -> ParsedSycmMemberMetrics:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_metrics(
        payload,
        business_day=business_day,
        section=section,
        raw=raw,
        fallback_platform_store_id=platform_store_id,
    )


def parse_metrics(
    payload: dict[str, Any],
    business_day: date,
    section: str,
    raw: bytes | None = None,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedSycmMemberMetrics:
    if section not in SECTION_PREFIXES:
        raise SycmMemberAnalysisPayloadError(f"Unsupported member metric section: {section}")

    response_code = _as_int(payload.get("code"))
    if response_code != 0:
        message = payload.get("message") or "unknown response error"
        raise SycmMemberAnalysisPayloadError(f"SYCM member response failed: {message}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise SycmMemberAnalysisPayloadError("The SYCM member response has no data object.")

    prefix = SECTION_PREFIXES[section]
    index_desc = payload.get("extra", {}).get("indexDesc")
    if not isinstance(index_desc, dict):
        index_desc = {}

    metrics: list[ParsedMetric] = []
    for code, entry in data.items():
        if not isinstance(entry, dict) or code in DIMENSION_CODES:
            continue
        if _is_nested_collection(entry):
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
                code=f"{prefix}{code}",
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
    return ParsedSycmMemberMetrics(
        platform_store_id=_platform_store_id(payload, data, fallback_platform_store_id),
        business_day=business_day,
        section=section,
        metrics=metrics,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=SECTION_ENDPOINT_KEYS[section],
        parser_version="sycm-member-analysis-v1",
    )


def load_and_parse_channel(
    path: Path,
    business_day: date,
    platform_store_id: str = "2200573698992",
) -> ParsedSycmMemberChannel:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_channel(
        payload,
        business_day=business_day,
        raw=raw,
        fallback_platform_store_id=platform_store_id,
    )


def parse_channel(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedSycmMemberChannel:
    response_code = _as_int(payload.get("code"))
    if response_code != 0:
        message = payload.get("message") or "unknown response error"
        raise SycmMemberAnalysisPayloadError(f"SYCM member channel response failed: {message}")

    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise SycmMemberAnalysisPayloadError(
            "The SYCM member channel response has no data.data list."
        )

    rows: list[ParsedMemberChannelRow] = []
    for item in data["data"]:
        if not isinstance(item, dict):
            continue
        rows.append(
            ParsedMemberChannelRow(
                row_order=len(rows) + 1,
                channel_name=_value_as_text(item.get("channelGroupName")),
                channel_link=_value_as_text(item.get("channelGroupLink")),
                new_members=_metric_decimal(item, "incrMbrCnt"),
                paid_new_members=_metric_decimal(item, "incrPaidMbrCnt"),
                recruit_conversion_rate=_metric_decimal(item, "recConvertRate"),
                new_member_paid_amount=_metric_decimal(item, "incrPayOrdAmt"),
                new_member_unit_price=_metric_decimal(item, "incrUnitPrice"),
                value_json=json.dumps(
                    {
                        key: _self_only_value(value)
                        for key, value in item.items()
                        if not key.lower().startswith("rival")
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
            )
        )

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    first_row = data["data"][0] if data["data"] and isinstance(data["data"][0], dict) else {}
    return ParsedSycmMemberChannel(
        platform_store_id=_platform_store_id(payload, first_row, fallback_platform_store_id),
        business_day=business_day,
        rows=rows,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key="sycm.domain.one_query.member_channel",
        parser_version="sycm-member-channel-v1",
    )


def _is_nested_collection(entry: dict[str, Any]) -> bool:
    value = entry.get("value")
    return isinstance(value, (dict, list))


def _platform_store_id(
    payload: dict[str, Any],
    data: dict[str, Any],
    fallback: str,
) -> str:
    direct = _value_as_text(data.get("sellerId"))
    if direct:
        return direct
    query = payload.get("extra", {}).get("queryParam")
    if isinstance(query, dict):
        for key in ("runAsUserId", "runasUserId", "mainUserId"):
            value = query.get(key)
            if value is not None:
                return str(value)
    return fallback


def _self_only_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _self_only_value(child)
            for key, child in value.items()
            if not key.lower().startswith("rival")
        }
    if isinstance(value, list):
        return [_self_only_value(item) for item in value]
    return value


def _metric_decimal(node: dict[str, Any], code: str) -> Decimal:
    return _as_decimal(_value(node.get(code))) or Decimal("0")


def _value(entry: object) -> object:
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def _value_as_text(entry: object) -> str:
    value = _value(entry)
    return "" if value is None else str(value)


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace('"', "").replace(",", "")
        if not value or value == "-":
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
