from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "brandsearch.pz.rpt_advertiser_sub_list"
PARSER_VERSION = "brandsearch-pz-v1"
MONEY_QUANTUM = Decimal("0.01")


class BrandSearchPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedBrandSearchReport:
    platform_store_id: str
    business_day: date
    impressions: Decimal | None
    search_requests: Decimal | None
    clicks: Decimal | None
    click_rate: Decimal | None
    click_visitors: Decimal | None
    item_cart_count: Decimal | None
    paid_amount: Decimal | None
    paid_order_count: Decimal | None
    conversion_rate: Decimal | None
    destination_clicks: Decimal | None
    interaction_clicks: Decimal | None
    destination_click_rate: Decimal | None
    shop_favorites: Decimal | None
    item_favorites: Decimal | None
    item_page_views: Decimal | None
    research_impressions: Decimal | None
    shop_page_views: Decimal | None
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str

    @property
    def metric_count(self) -> int:
        return sum(
            value is not None
            for value in (
                self.impressions,
                self.search_requests,
                self.clicks,
                self.click_rate,
                self.click_visitors,
                self.item_cart_count,
                self.paid_amount,
                self.paid_order_count,
                self.conversion_rate,
                self.destination_clicks,
                self.interaction_clicks,
                self.destination_click_rate,
                self.shop_favorites,
                self.item_favorites,
                self.item_page_views,
                self.research_impressions,
                self.shop_page_views,
            )
        )


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedBrandSearchReport:
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
) -> ParsedBrandSearchReport:
    data = payload.get("data")
    report = data.get("rptQueryResp") if isinstance(data, dict) else None
    rows = report.get("rptDataDaily") if isinstance(report, dict) else None
    if not isinstance(rows, list):
        raise BrandSearchPayloadError(
            "The PZ brand-search response has no data.rptQueryResp.rptDataDaily list."
        )

    row = next(
        (
            candidate
            for candidate in rows
            if isinstance(candidate, dict)
            and _parse_business_day(candidate.get("thedate")) == business_day
        ),
        None,
    )
    if row is None:
        raise BrandSearchPayloadError(
            f"The PZ brand-search response has no daily row for {business_day}."
        )

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedBrandSearchReport(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        impressions=_metric_decimal(row, "impression"),
        search_requests=_metric_decimal(row, "requestCnt"),
        clicks=_metric_decimal(row, "click"),
        click_rate=_metric_decimal(row, "ctr"),
        click_visitors=_metric_decimal(row, "click_uv"),
        item_cart_count=_metric_decimal(row, "carttotal"),
        paid_amount=_money_from_cents(row, "transactiontotal"),
        paid_order_count=_metric_decimal(row, "transactionshippingtotal"),
        conversion_rate=_metric_decimal(row, "cpt_cvr"),
        destination_clicks=_metric_decimal(row, "shopclick"),
        interaction_clicks=_metric_decimal(row, "interactclick"),
        destination_click_rate=_metric_decimal(row, "shopctr"),
        shop_favorites=_metric_decimal(row, "favshoptotal"),
        item_favorites=_metric_decimal(row, "favitemtotal"),
        item_page_views=_metric_decimal(row, "item_view_cnt"),
        research_impressions=_metric_decimal(row, "research_impression"),
        shop_page_views=_metric_decimal(row, "shop_view_cnt"),
        response_code=0,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _metric_decimal(row: dict[str, Any], field: str) -> Decimal | None:
    return _as_decimal(row.get(field))


def _money_from_cents(row: dict[str, Any], field: str) -> Decimal | None:
    value = _as_decimal(row.get(field))
    if value is None:
        return None
    return (value / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _parse_business_day(value: object) -> date | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
