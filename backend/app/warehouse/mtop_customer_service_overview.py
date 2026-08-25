from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "mtop.alibaba.sycm.domain.onequery.customer_service_kpi"
PARSER_VERSION = "mtop-customer-service-overview-v1"
MONEY_QUANTUM = Decimal("0.01")
MONEY_METRIC_CODES = {
    "customerServiceGmv",
    "customerServiceSalePrice",
    "sucRefundAmount",
    "netPayAmt",
}

CUSTOMER_SERVICE_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "customerServiceGmv": ("customerServiceGmv",),
    "customerServiceSaleCnt": ("customerServiceSaleCnt",),
    "customerServiceSaleRatio": ("customerServiceSaleRatio",),
    "customerServiceSalePrice": ("customerServiceSalePrice",),
    "sucRefundAmount": ("sucRefundAmount", "sucRefundAmt"),
    "netPayAmt": ("netPayAmt", "csNetPayAmt"),
    "consultUserCnt": ("consultUserCnt",),
    "customerServiceRecUserCnt": ("customerServiceRecUserCnt",),
    "wwConsultPayRate": ("wwConsultPayRate",),
    "avgReplyInterval": ("avgReplyInterval",),
    "customerAllSateRate": ("customerAllSateRate",),
    "wwUserReplayRate": ("wwUserReplayRate",),
    "jtkCaseEndAvgDur": (
        "jtkCaseEndAvgDur",
        "rfdAvgEndTime",
        "rfdOverTime",
    ),
    "thtkCaseEndAvgDur": (
        "thtkCaseEndAvgDur",
        "rfdGoodsAvgEndTime",
        "rfdGoodsOverTime",
    ),
    "pltfHelpRate": ("pltfHelpRate",),
    "pltfRespRate": ("pltfRespRate",),
}
ALL_METRIC_ALIASES = {
    alias
    for aliases in CUSTOMER_SERVICE_METRIC_ALIASES.values()
    for alias in aliases
}


class MtopCustomerServiceOverviewPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedMtopCustomerServiceOverview:
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
) -> ParsedMtopCustomerServiceOverview:
    raw = path.read_bytes()
    payload = _load_json_or_jsonp(raw)
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
) -> ParsedMtopCustomerServiceOverview:
    response_code = _validate_success(payload)
    container = _find_metric_container(payload, business_day)
    metrics = {}
    for code, aliases in CUSTOMER_SERVICE_METRIC_ALIASES.items():
        value = _metric_decimal(container, aliases)
        if value is not None and code in MONEY_METRIC_CODES:
            value = value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        metrics[code] = value
    if not any(value is not None for value in metrics.values()):
        raise MtopCustomerServiceOverviewPayloadError(
            "The customer-service response contains no recognized KPI values."
        )

    platform_store_id = (
        _recursive_find_text(
            payload,
            ("sellerId", "shopId", "mainUserId", "runAsUserId", "userId"),
        )
        or fallback_platform_store_id
    )
    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedMtopCustomerServiceOverview(
        platform_store_id=platform_store_id,
        business_day=business_day,
        metrics=metrics,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _load_json_or_jsonp(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8-sig").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.match(r"^[^(]+\((.*)\)\s*;?\s*$", text, flags=re.DOTALL)
        if match is None:
            raise MtopCustomerServiceOverviewPayloadError(
                "The saved customer-service response is neither JSON nor JSONP."
            )
        payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise MtopCustomerServiceOverviewPayloadError(
            "The saved customer-service response root is not an object."
        )
    return payload


def _validate_success(payload: dict[str, Any]) -> int:
    ret = payload.get("ret")
    if isinstance(ret, list):
        if not any(str(item).startswith("SUCCESS::") for item in ret):
            raise MtopCustomerServiceOverviewPayloadError(
                f"MTop customer-service request failed: {ret}"
            )
    if payload.get("success") is False:
        message = payload.get("message") or payload.get("msg") or "unknown response error"
        raise MtopCustomerServiceOverviewPayloadError(
            f"MTop customer-service request failed: {message}"
        )
    data = payload.get("data")
    if isinstance(data, dict) and data.get("fail") is True:
        message = data.get("message") or data.get("msg") or "unknown response error"
        raise MtopCustomerServiceOverviewPayloadError(
            f"MTop customer-service request failed: {message}"
        )

    code = _as_int(payload.get("code"))
    if code not in (0, 200):
        message = payload.get("message") or payload.get("msg") or "unknown response error"
        raise MtopCustomerServiceOverviewPayloadError(
            f"MTop customer-service response failed: {message}"
        )
    return code


def _find_metric_container(
    payload: dict[str, Any],
    business_day: date,
) -> dict[str, Any]:
    candidates: list[tuple[int, dict[str, Any]]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            metric_score = sum(key in ALL_METRIC_ALIASES for key in node)
            if metric_score:
                day_bonus = 100 if _node_day(node) == business_day else 0
                candidates.append((day_bonus + metric_score, node))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    if not candidates:
        raise MtopCustomerServiceOverviewPayloadError(
            "The customer-service response has no recognized KPI container."
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _node_day(node: dict[str, Any]) -> date | None:
    for key in ("statDate", "date", "ds", "businessDay"):
        value = _extract_scalar(node.get(key))
        if value is None:
            continue
        text = str(value).strip()
        for pattern in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
    return None


def _metric_decimal(
    container: dict[str, Any],
    aliases: tuple[str, ...],
) -> Decimal | None:
    for alias in aliases:
        if alias in container:
            return _as_decimal(_extract_scalar(container.get(alias)))
    return None


def _extract_scalar(value: object) -> object:
    if isinstance(value, dict):
        for key in (
            "value",
            "absolute",
            "metricValue",
            "metricStringValue",
            "current",
            "data",
        ):
            if key in value:
                extracted = _extract_scalar(value.get(key))
                if extracted is not None:
                    return extracted
        return None
    if isinstance(value, list):
        for item in value:
            extracted = _extract_scalar(item)
            if extracted is not None:
                return extracted
        return None
    return value


def _recursive_find_text(node: object, keys: tuple[str, ...]) -> str:
    if isinstance(node, dict):
        for key in keys:
            if key not in node:
                continue
            value = _extract_scalar(node.get(key))
            if value is not None and str(value).strip():
                return str(value).strip()
        for value in node.values():
            found = _recursive_find_text(value, keys)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _recursive_find_text(item, keys)
            if found:
                return found
    return ""


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result / Decimal("100") if is_percent else result


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
