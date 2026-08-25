from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "mtop.guangguang.creator.content_asset_key_indicators"
PARSER_VERSION = "mtop-content-overview-v1"
MONEY_QUANTUM = Decimal("0.01")

CONTENT_METRIC_CODES = (
    "clickUv",
    "consumePv",
    "pctr",
    "freeConsumePv",
    "detailIpvUv",
    "ipvContentCnt",
    "publishContentCnt",
    "gmvPct",
    "ipvUv",
    "notFreeConsumePv",
    "detailIpvContentCnt",
    "detailIpvPv",
    "publicContentCnt",
    "payOrderCntZcLast",
    "itrtPv",
    "publishAllContentCnt",
    "expoUv",
    "consumeUv",
    "cartUv",
    "ipvRate",
    "consumeContentCnt",
    "payBuyerCntZc",
    "ipvPv",
    "payAmtZcLast",
    "itrtUv",
    "itrtRate",
    "consumeTimeAvgPv",
    "uctr",
    "cartPv",
)


class MtopContentOverviewPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedMtopContentOverview:
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
) -> ParsedMtopContentOverview:
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
) -> ParsedMtopContentOverview:
    _validate_mtop_success(payload)
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("fail") is True:
        raise MtopContentOverviewPayloadError("The MTop content response reports a failure.")

    model = data.get("model")
    rows = model.get("result") if isinstance(model, dict) else None
    if not isinstance(rows, list):
        raise MtopContentOverviewPayloadError("The MTop content response has no result list.")

    target = next(
        (
            row
            for row in rows
            if isinstance(row, dict) and _row_date(row) == business_day
        ),
        None,
    )
    if target is None:
        raise MtopContentOverviewPayloadError(
            f"The MTop content response has no row for {business_day}."
        )

    metrics = {
        code: _absolute_decimal(target.get(code))
        for code in CONTENT_METRIC_CODES
    }
    if metrics["payAmtZcLast"] is not None:
        metrics["payAmtZcLast"] = metrics["payAmtZcLast"].quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedMtopContentOverview(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        metrics=metrics,
        response_code=0,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _validate_mtop_success(payload: dict[str, Any]) -> None:
    ret = payload.get("ret")
    if not isinstance(ret, list) or not any(str(item).startswith("SUCCESS::") for item in ret):
        raise MtopContentOverviewPayloadError(f"MTop content request failed: {ret}")


def _row_date(row: dict[str, Any]) -> date | None:
    entry = row.get("date")
    value = entry.get("absolute") if isinstance(entry, dict) else row.get("ds")
    if value is None:
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _absolute_decimal(entry: object) -> Decimal | None:
    if not isinstance(entry, dict):
        return None
    return _as_decimal(entry.get("absolute"))


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
