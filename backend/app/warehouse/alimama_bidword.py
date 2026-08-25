from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.local_database import PROMOTION_BIDWORD_METRICS


ENDPOINT_KEY = "alimama.report.query.bidword"
PARSER_VERSION = "alimama-bidword-v1"


class AlimamaBidwordPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class PromotionBidwordRow:
    scene_name: str
    campaign_id: str
    campaign_name: str
    adgroup_id: str
    adgroup_name: str
    bidword_id: str
    bidword_name: str
    bidword_package_id: str
    bidword_package_name: str
    bidword_type: str
    automatch_type: str
    product_id: str
    product_name: str
    metrics: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class ParsedAlimamaBidwordReport:
    platform_store_id: str
    business_day: date
    rows: tuple[PromotionBidwordRow, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return len(self.rows) * len(PROMOTION_BIDWORD_METRICS)


_METRIC_FIELDS = {
    "展现量": "adPv",
    "点击量": "click",
    "点击率": "ctr",
    "花费": "charge",
    "平均点击花费": "ecpc",
    "旺旺咨询量": "wwNum",
    "直接购物车数": "cartDirNum",
    "总购物车数": "cartInshopNum",
    "总收藏数": "colNum",
    "加购率": "cartRate",
    "加购成本": "cartCost",
    "直接成交笔数": "alipayDirNum",
    "总成交笔数": "alipayInshopNum",
    "直接成交金额": "alipayDirAmt",
    "总成交金额": "alipayInshopAmt",
    "成交人数": "alipayInshopUv",
    "人均成交金额": "alipayInshopAmtAvg",
    "投入产出比": "roi",
    "总成交成本": "alipayInshopCost",
    "入会量": "rhNum",
    "入会率": "rhRate",
    "会员首购人数": "hySgUv",
    "会员成交金额": "hyPayAmt",
    "成交新客数": "newAlipayInshopUv",
    "成交新客占比": "newAlipayInshopUvRate",
}


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedAlimamaBidwordReport:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlimamaBidwordPayloadError(
            "The Alimama bidword response is not valid JSON."
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
) -> ParsedAlimamaBidwordReport:
    if not isinstance(payload, dict):
        raise AlimamaBidwordPayloadError("The Alimama bidword response must be an object.")
    page_payloads = payload.get("pages")
    source_payloads = (
        [item for item in page_payloads if isinstance(item, dict)]
        if isinstance(page_payloads, list)
        else [payload]
    )
    rows_by_key: dict[tuple[str, str, str, str, str, str, str], PromotionBidwordRow] = {}
    for page_payload in source_payloads:
        if _response_code(page_payload) != 0:
            raise AlimamaBidwordPayloadError("The Alimama bidword response failed.")
        data = page_payload.get("data")
        rows = data.get("list") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise AlimamaBidwordPayloadError(
                "The Alimama bidword response has no data.list."
            )
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            row_day = _parse_day(raw_row.get("thedate") or raw_row.get("startTime"))
            if row_day is not None and row_day != business_day:
                continue
            campaign_id = _text(raw_row.get("campaignId")) or ""
            adgroup_id = _text(raw_row.get("adgroupId")) or ""
            bidword_id = _text(raw_row.get("bidwordId")) or ""
            bidword_type = _text(raw_row.get("bidWordType")) or "word"
            if not campaign_id or not adgroup_id or not bidword_id:
                continue
            product = _product(raw_row)
            row = PromotionBidwordRow(
                scene_name=_text(raw_row.get("scene1Name")) or "",
                campaign_id=campaign_id,
                campaign_name=_text(raw_row.get("campaignName")) or "",
                adgroup_id=adgroup_id,
                adgroup_name=_text(raw_row.get("adgroupName")) or "",
                bidword_id=bidword_id,
                bidword_name=_text(raw_row.get("originalWord")) or "",
                bidword_package_id=_text(raw_row.get("bidwordPkgId")) or "",
                bidword_package_name=_text(raw_row.get("bidwordPkgName")) or "",
                bidword_type=bidword_type,
                automatch_type=_text(raw_row.get("isAutomatch")) or "",
                product_id=product[0],
                product_name=product[1],
                metrics=tuple(
                    _decimal(raw_row.get(_METRIC_FIELDS[column]))
                    for column in PROMOTION_BIDWORD_METRICS
                ),
            )
            rows_by_key[
                (
                    campaign_id,
                    adgroup_id,
                    bidword_id,
                    row.bidword_package_id,
                    bidword_type,
                    row.automatch_type,
                    product[0],
                )
            ] = row
    return ParsedAlimamaBidwordReport(
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
        _text(row.get("promotionId") or row.get("blackCreativePromotionId") or promotion.get("promotionId")) or "",
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
