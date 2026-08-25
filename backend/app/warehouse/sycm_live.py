from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


LIVE_ENDPOINT = "sycm.s_content.live"
PARSER_VERSION = "sycm-live-v1"


class SycmLivePayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedLiveOverview:
    platform_store_id: str
    metrics: tuple[Decimal | None, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = f"{LIVE_ENDPOINT}.amount_compose_overview"
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return sum(value is not None for value in self.metrics)


@dataclass(frozen=True)
class ParsedLiveStorePerformance:
    platform_store_id: str
    metrics: tuple[Decimal | None, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = f"{LIVE_ENDPOINT}.click_transform"
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return sum(value is not None for value in self.metrics)


@dataclass(frozen=True)
class LiveTalentRow:
    talent_id: str
    talent_name: str
    metrics: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class ParsedLiveTalent:
    platform_store_id: str
    rows: tuple[LiveTalentRow, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = f"{LIVE_ENDPOINT}.cooperate_room_list"
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return len(self.rows)


def load_and_parse_overview(path: Path, fallback_platform_store_id: str) -> ParsedLiveOverview:
    raw = path.read_bytes()
    payload = _load_json(raw)
    data = _self_data(payload)
    codes = (
        "broadcastLivePayAmt", "payAmtPerThousand", "shopPlayPayAmt",
        "broadcastLookUv", "visitUvPerHour", "afterPlayPayAmt",
        "broadcastPayAmt", "broadcastPlayDuration",
    )
    return ParsedLiveOverview(
        platform_store_id=str(_value(data.get("sellerId")) or fallback_platform_store_id),
        metrics=tuple(_metric(data, code) for code in codes),
        response_code=_response_code(payload),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_bytes=len(raw),
    )


def load_and_parse_store_performance(path: Path, fallback_platform_store_id: str) -> ParsedLiveStorePerformance:
    raw = path.read_bytes()
    payload = _load_json(raw)
    data = _self_data(payload)
    codes = (
        "broadcastLookUv", "broadcastItemClickUv", "lookItemClickRate",
        "broadcastDealUv", "clickDealRate", "livePlayPayAmt", "unitPrice",
        "broadcastDealItemCnt", "broadcastDealOrderCnt",
    )
    return ParsedLiveStorePerformance(
        platform_store_id=str(_value(data.get("sellerId")) or fallback_platform_store_id),
        metrics=tuple(_metric(data, code) for code in codes),
        response_code=_response_code(payload),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_bytes=len(raw),
    )


def load_and_parse_talent(path: Path, fallback_platform_store_id: str) -> ParsedLiveTalent:
    raw = path.read_bytes()
    payload = _load_json(raw)
    pages = payload.get("pages")
    page_payloads = pages if isinstance(pages, list) else [payload]
    rows: list[LiveTalentRow] = []
    for page in page_payloads:
        if not isinstance(page, dict):
            continue
        data = page.get("data")
        page_rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(page_rows, list):
            raise SycmLivePayloadError("The live talent response has no data.data list.")
        for item in page_rows:
            if not isinstance(item, dict):
                continue
            talent_id = str(_value(item.get("coopActId")) or "")
            if not talent_id:
                continue
            rows.append(
                LiveTalentRow(
                    talent_id=talent_id,
                    talent_name=str(_value(item.get("coopLiveName")) or ""),
                    metrics=tuple(
                        _metric(item, code)
                        for code in (
                            "liveSessionCount", "goodsClickUv", "goodsClickCnt",
                            "goodsAddCartUv", "goodsAddCartCnt", "goodsDealUv",
                            "goodsDealAmt", "goodsDealCnt", "goodsSingleAmt",
                            "dealPieceCnt", "dealOrderCnt",
                        )
                    ),
                )
            )
    if not rows:
        raise SycmLivePayloadError("The live talent response contains no talent rows.")
    return ParsedLiveTalent(
        platform_store_id=fallback_platform_store_id,
        rows=tuple(rows),
        response_code=_response_code(page_payloads[0]) if page_payloads else 0,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_bytes=len(raw),
    )


def _load_json(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SycmLivePayloadError("The SYCM live response is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise SycmLivePayloadError("The SYCM live response must be a JSON object.")
    code = _response_code(payload)
    if code != 0:
        raise SycmLivePayloadError(f"SYCM live response failed with code {code}.")
    return payload


def _self_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    self_data = data.get("self") if isinstance(data, dict) else None
    if not isinstance(self_data, dict):
        raise SycmLivePayloadError("The SYCM live response has no data.self object.")
    return self_data


def _response_code(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("code", 0))
    except (TypeError, ValueError):
        return 0


def _value(value: Any) -> Any:
    return value.get("value") if isinstance(value, dict) else value


def _metric(data: dict[str, Any], code: str) -> Decimal | None:
    value = _value(data.get(code))
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
