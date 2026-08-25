from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.local_database import PROMOTION_CAMPAIGN_METRICS


ENDPOINT_KEY = "alimama.report.query.campaign"
PARSER_VERSION = "alimama-campaign-v1"


class AlimamaCampaignPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class PromotionCampaignRow:
    scene_name: str
    campaign_id: str
    campaign_name: str
    metrics: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class ParsedAlimamaCampaignReport:
    platform_store_id: str
    business_day: date
    rows: tuple[PromotionCampaignRow, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return len(self.rows) * len(PROMOTION_CAMPAIGN_METRICS)


_METRIC_FIELDS: dict[str, str] = {
    "展现量": "adPv",
    "点击量": "click",
    "花费": "charge",
    "点击率": "ctr",
    "平均点击花费": "ecpc",
    "千次展现花费": "ecpm",
    "总预售成交金额": "prepayInshopAmt",
    "总预售成交笔数": "prepayInshopNum",
    "直接预售成交金额": "prepayDirAmt",
    "直接预售成交笔数": "prepayDirNum",
    "间接预售成交金额": "prepayIndirAmt",
    "间接预售成交笔数": "prepayIndirNum",
    "直接成交金额": "alipayDirAmt",
    "间接成交金额": "alipayIndirAmt",
    "总成交金额": "alipayInshopAmt",
    "总成交笔数": "alipayInshopNum",
    "直接成交笔数": "alipayDirNum",
    "间接成交笔数": "alipayIndirNum",
    "点击转化率": "cvr",
    "投入产出比": "roi",
    "总成交成本": "alipayInshopCost",
    "总购物车数": "cartInshopNum",
    "直接购物车数": "cartDirNum",
    "间接购物车数": "cartIndirNum",
    "加购率": "cartRate",
    "宝贝收藏数": "itemColInshopNum",
    "店铺收藏数": "shopColDirNum",
    "店铺收藏成本": "shopColInshopCost",
    "总收藏加购数": "colCartNum",
    "总收藏加购成本": "colCartCost",
    "宝贝收藏加购数": "itemColCart",
    "宝贝收藏加购成本": "itemColCartCost",
    "总收藏数": "colNum",
    "宝贝收藏成本": "itemColInshopCost",
    "宝贝收藏率": "itemColInshopRate",
    "加购成本": "cartCost",
    "拍下订单笔数": "gmvInshopNum",
    "拍下订单金额": "gmvInshopAmt",
    "直接收藏宝贝数": "itemColDirNum",
    "间接收藏宝贝数": "itemColIndirNum",
    "优惠券领取量": "couponShopNum",
    "购物金充值笔数": "shoppingNum",
    "购物金充值金额": "shoppingAmt",
    "旺旺咨询量": "wwNum",
    "引导访问量": "inshopPv",
    "引导访问人数": "inshopUv",
    "引导访问潜客数": "inshopPotentialUv",
    "引导访问潜客占比": "inshopPotentialUvRate",
    "入会率": "rhRate",
    "入会量": "rhNum",
    "引导访问率": "inshopPvRate",
    "深度访问量": "deepInshopPv",
    "平均访问页面数": "avgAccessPageNum",
    "成交新客数": "newAlipayInshopUv",
    "成交新客占比": "newAlipayInshopUvRate",
    "会员首购人数": "hySgUv",
    "会员成交金额": "hyPayAmt",
    "会员成交笔数": "hyPayNum",
    "成交人数": "alipayInshopUv",
    "人均成交笔数": "alipayInshopNumAvg",
    "人均成交金额": "alipayInshopAmtAvg",
    "自然流量转化金额": "naturalPayAmt",
    "自然流量曝光量": "orgNaturalPv",
}


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedAlimamaCampaignReport:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlimamaCampaignPayloadError("The Alimama campaign response is not valid JSON.") from exc
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
) -> ParsedAlimamaCampaignReport:
    if not isinstance(payload, dict):
        raise AlimamaCampaignPayloadError("The Alimama campaign response must be an object.")
    page_payloads = payload.get("pages")
    if isinstance(page_payloads, list):
        source_payloads = [item for item in page_payloads if isinstance(item, dict)]
    else:
        source_payloads = [payload]

    rows_by_id: dict[str, PromotionCampaignRow] = {}
    for page_payload in source_payloads:
        response_code = _response_code(page_payload)
        if response_code != 0:
            raise AlimamaCampaignPayloadError(
                f"The Alimama campaign response failed with code {response_code}."
            )
        data = page_payload.get("data")
        rows_value = data.get("list") if isinstance(data, dict) else None
        if not isinstance(rows_value, list):
            raise AlimamaCampaignPayloadError("The Alimama campaign response has no data.list.")
        for raw_row in rows_value:
            if not isinstance(raw_row, dict):
                continue
            campaign_id = _text(raw_row.get("campaignId"))
            if not campaign_id:
                continue
            row_day = _parse_day(raw_row.get("thedate") or raw_row.get("startTime"))
            if row_day is not None and row_day != business_day:
                continue
            rows_by_id[campaign_id] = PromotionCampaignRow(
                scene_name=_text(raw_row.get("scene1Name")) or "",
                campaign_id=campaign_id,
                campaign_name=_text(raw_row.get("campaignName")) or "",
                metrics=tuple(
                    _decimal(raw_row.get(_METRIC_FIELDS[column]))
                    for column in PROMOTION_CAMPAIGN_METRICS
                ),
            )

    return ParsedAlimamaCampaignReport(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=tuple(rows_by_id.values()),
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
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
    if value is None:
        return None
    return str(value).strip()


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
