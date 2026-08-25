from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.local_database import PROMOTION_ADGROUP_METRICS


ENDPOINT_KEY = "alimama.report.query.adgroup"
PARSER_VERSION = "alimama-adgroup-v1"


class AlimamaAdgroupPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class PromotionAdgroupRow:
    scene_name: str
    campaign_id: str
    campaign_name: str
    adgroup_id: str
    adgroup_name: str
    product_id: str
    product_name: str
    metrics: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class ParsedAlimamaAdgroupReport:
    platform_store_id: str
    business_day: date
    rows: tuple[PromotionAdgroupRow, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return len(self.rows) * len(PROMOTION_ADGROUP_METRICS)


_METRIC_FIELDS = {
    "展现量": "adPv",
    "点击量": "click",
    "花费": "charge",
    "点击率": "ctr",
    "平均点击花费": "ecpc",
    "总成交金额": "alipayInshopAmt",
    "总成交笔数": "alipayInshopNum",
    "点击转化率": "cvr",
    "总购物车数": "cartInshopNum",
    "宝贝收藏数": "itemColInshopNum",
    "店铺收藏数": "shopColDirNum",
    "总收藏数": "colNum",
    "宝贝收藏成本": "itemColInshopCost",
}


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedAlimamaAdgroupReport:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlimamaAdgroupPayloadError(
            "The Alimama adgroup response is not valid JSON."
        ) from exc
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
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedAlimamaAdgroupReport:
    if not isinstance(payload, dict):
        raise AlimamaAdgroupPayloadError("The Alimama adgroup response must be an object.")
    page_payloads = payload.get("pages")
    source_payloads = (
        [item for item in page_payloads if isinstance(item, dict)]
        if isinstance(page_payloads, list)
        else [payload]
    )
    rows_by_key: dict[tuple[str, str], PromotionAdgroupRow] = {}
    for page_payload in source_payloads:
        if _response_code(page_payload) != 0:
            raise AlimamaAdgroupPayloadError("The Alimama adgroup response failed.")
        data = page_payload.get("data")
        rows = data.get("list") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise AlimamaAdgroupPayloadError(
                "The Alimama adgroup response has no data.list."
            )
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            row_day = _parse_day(raw_row.get("thedate") or raw_row.get("startTime"))
            if row_day is not None and row_day != business_day:
                continue
            campaign_id = _text(raw_row.get("campaignId")) or ""
            adgroup_id = _text(raw_row.get("adgroupId")) or ""
            if not campaign_id or not adgroup_id:
                continue
            product = _product(raw_row)
            rows_by_key[(campaign_id, adgroup_id)] = PromotionAdgroupRow(
                scene_name=_text(raw_row.get("scene1Name")) or "",
                campaign_id=campaign_id,
                campaign_name=_text(raw_row.get("campaignName")) or "",
                adgroup_id=adgroup_id,
                adgroup_name=_text(raw_row.get("adgroupName")) or "",
                product_id=product[0],
                product_name=product[1],
                metrics=tuple(
                    _decimal(raw_row.get(_METRIC_FIELDS[column]))
                    for column in PROMOTION_ADGROUP_METRICS
                ),
            )
    return ParsedAlimamaAdgroupReport(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=tuple(rows_by_key.values()),
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
    )


def _product(row: dict[str, Any]) -> tuple[str, str]:
    promotions = row.get("promotions")
    promotion = promotions[0] if isinstance(promotions, list) and promotions else {}
    if not isinstance(promotion, dict):
        promotion = {}
    return (
        _text(row.get("promotionId") or promotion.get("promotionId")) or "",
        _text(row.get("promotionName") or promotion.get("promotionName")) or "",
    )


def _response_code(payload: dict[str, Any]) -> int | None:
    info = payload.get("info")
    if isinstance(info, dict) and info.get("ok") is True:
        return 0
    for value in (payload, payload.get("data"), payload.get("content")):
        if isinstance(value, dict) and value.get("code") is not None:
            try:
                return int(value["code"])
            except (TypeError, ValueError):
                return None
    return None


def _parse_day(value: object) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _text(value: object) -> str | None:
    return None if value is None else str(value).strip()


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
