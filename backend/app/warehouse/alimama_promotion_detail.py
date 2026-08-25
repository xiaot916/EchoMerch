from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.local_database import PROMOTION_CONTENT_METRICS, PROMOTION_ITEM_METRICS


ITEM_ENDPOINT_KEY = "alimama.report.query.item_promotion"
CONTENT_ENDPOINT_KEY = "alimama.report.query.other_promotion"
PARSER_VERSION = "alimama-promotion-detail-v1"


class AlimamaPromotionDetailPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class PromotionDetailRow:
    scene_name: str
    campaign_id: str
    campaign_name: str
    subject_id: str
    subject_name: str
    subject_type: str
    metrics: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class ParsedAlimamaPromotionDetailReport:
    platform_store_id: str
    business_day: date
    rows: tuple[PromotionDetailRow, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        metric_columns = (
            PROMOTION_ITEM_METRICS
            if self.endpoint_key == ITEM_ENDPOINT_KEY
            else PROMOTION_CONTENT_METRICS
        )
        return len(self.rows) * len(metric_columns)


_ITEM_METRIC_FIELDS: dict[str, str] = {
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
    "点击转化率": "cvr",
    "投入产出比": "roi",
    "总成交成本": "alipayInshopCost",
    "成交人数": "alipayInshopUv",
    "人均成交笔数": "alipayInshopNumAvg",
    "人均成交金额": "alipayInshopAmtAvg",
    "入会量": "rhNum",
    "入会率": "rhRate",
    "会员首购人数": "hySgUv",
    "会员成交笔数": "hyPayNum",
    "会员成交金额": "hyPayAmt",
    "成交新客数": "newAlipayInshopUv",
    "成交新客占比": "newAlipayInshopUvRate",
    "自然流量转化金额": "naturalPayAmt",
    "自然流量曝光量": "orgNaturalPv",
}
_CONTENT_METRIC_FIELDS: dict[str, str] = {
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


def load_and_parse_item(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedAlimamaPromotionDetailReport:
    return _load_and_parse(
        path,
        business_day,
        fallback_platform_store_id,
        endpoint_key=ITEM_ENDPOINT_KEY,
        metric_fields=_ITEM_METRIC_FIELDS,
        metric_columns=PROMOTION_ITEM_METRICS,
    )


def load_and_parse_content(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedAlimamaPromotionDetailReport:
    return _load_and_parse(
        path,
        business_day,
        fallback_platform_store_id,
        endpoint_key=CONTENT_ENDPOINT_KEY,
        metric_fields=_CONTENT_METRIC_FIELDS,
        metric_columns=PROMOTION_CONTENT_METRICS,
    )


def _load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str,
    *,
    endpoint_key: str,
    metric_fields: dict[str, str],
    metric_columns: tuple[str, ...],
) -> ParsedAlimamaPromotionDetailReport:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlimamaPromotionDetailPayloadError(
            "The Alimama promotion detail response is not valid JSON."
        ) from exc
    return _parse_payload(
        payload,
        business_day=business_day,
        raw=raw,
        fallback_platform_store_id=fallback_platform_store_id,
        endpoint_key=endpoint_key,
        metric_fields=metric_fields,
        metric_columns=metric_columns,
    )


def _parse_payload(
    payload: dict[str, Any],
    *,
    business_day: date,
    raw: bytes | None,
    fallback_platform_store_id: str,
    endpoint_key: str,
    metric_fields: dict[str, str],
    metric_columns: tuple[str, ...],
) -> ParsedAlimamaPromotionDetailReport:
    if not isinstance(payload, dict):
        raise AlimamaPromotionDetailPayloadError(
            "The Alimama promotion detail response must be an object."
        )
    page_payloads = payload.get("pages")
    source_payloads = (
        [item for item in page_payloads if isinstance(item, dict)]
        if isinstance(page_payloads, list)
        else [payload]
    )
    rows_by_key: dict[tuple[str, str], PromotionDetailRow] = {}
    for page_payload in source_payloads:
        response_code = _response_code(page_payload)
        if response_code != 0:
            raise AlimamaPromotionDetailPayloadError(
                f"The Alimama promotion detail response failed with code {response_code}."
            )
        data = page_payload.get("data")
        rows_value = data.get("list") if isinstance(data, dict) else None
        if not isinstance(rows_value, list):
            raise AlimamaPromotionDetailPayloadError(
                "The Alimama promotion detail response has no data.list."
            )
        for raw_row in rows_value:
            if not isinstance(raw_row, dict):
                continue
            row_day = _parse_day(raw_row.get("thedate") or raw_row.get("startTime"))
            if row_day is not None and row_day != business_day:
                continue
            campaign_id = _text(raw_row.get("campaignId")) or ""
            subject_id = _text(
                raw_row.get("promotionId") or raw_row.get("blackCreativePromotionId")
            ) or ""
            if not subject_id:
                continue
            rows_by_key[(campaign_id, subject_id)] = PromotionDetailRow(
                scene_name=_text(raw_row.get("scene1Name")) or "",
                campaign_id=campaign_id,
                campaign_name=_text(raw_row.get("campaignName")) or "",
                subject_id=subject_id,
                subject_name=_text(raw_row.get("promotionName")) or "",
                subject_type=_text(
                    raw_row.get("subPromotionTypeName") or raw_row.get("subPromotionTypeStr")
                ) or "",
                metrics=tuple(
                    _decimal(raw_row.get(metric_fields[column])) for column in metric_columns
                ),
            )
    return ParsedAlimamaPromotionDetailReport(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=tuple(rows_by_key.values()),
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
        endpoint_key=endpoint_key,
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
