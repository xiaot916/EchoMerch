from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "mtop.taobao.argus.getAllItemCurrentPriceList"
PARSER_VERSION = "taobao-current-price-items-v1"


class TaobaoCurrentPricePayloadError(ValueError):
    pass


@dataclass(frozen=True)
class TaobaoCurrentPriceItemRow:
    item_id: str
    item_title: str
    attention: str
    risk_tag: str
    normal_promotion_details: str
    predicted_promotion_details: str
    risk_promotion_details: str
    item_detail_url: str
    main_picture: str
    low_price: Decimal | None
    low_price_lower_bound: Decimal | None
    low_price_upper_bound: Decimal | None
    original_price_lower_bound: Decimal | None
    original_price_upper_bound: Decimal | None
    normal_predict_price_lower_bound: Decimal | None
    normal_predict_price_upper_bound: Decimal | None
    predict_price_lower_bound: Decimal | None
    predict_price_upper_bound: Decimal | None
    sku_count: Decimal | None

    @property
    def metric_count(self) -> int:
        return sum(value is not None for value in (
            self.low_price, self.low_price_lower_bound, self.low_price_upper_bound,
            self.original_price_lower_bound, self.original_price_upper_bound,
            self.normal_predict_price_lower_bound, self.normal_predict_price_upper_bound,
            self.predict_price_lower_bound, self.predict_price_upper_bound, self.sku_count,
        ))


@dataclass(frozen=True)
class ParsedTaobaoCurrentPriceItems:
    platform_store_id: str
    business_day: date
    rows: list[TaobaoCurrentPriceItemRow]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return sum(row.metric_count for row in self.rows)


def load_and_parse(path: Path, business_day: date, fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID) -> ParsedTaobaoCurrentPriceItems:
    raw = path.read_bytes()
    return parse_payload(json.loads(raw.decode("utf-8")), business_day=business_day, raw=raw, fallback_platform_store_id=fallback_platform_store_id)


def parse_payload(payload: dict[str, Any], *, business_day: date, raw: bytes | None = None, fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID) -> ParsedTaobaoCurrentPriceItems:
    pages = payload.get("pages") if isinstance(payload, dict) else None
    source_pages = pages if isinstance(pages, list) else [payload]
    parsed: list[TaobaoCurrentPriceItemRow] = []
    for page in source_pages:
        if not isinstance(page, dict):
            continue
        rows = _find_items(page)
        code = _response_code(page)
        if code not in (0, 200, None):
            raise TaobaoCurrentPricePayloadError(f"Taobao current-price response failed: code={code}")
        if rows is None:
            raise TaobaoCurrentPricePayloadError("Taobao current-price response has no item list.")
        parsed.extend(_parse_row(row) for row in rows if isinstance(row, dict))
    parsed = list({row.item_id: row for row in parsed}.values())
    return ParsedTaobaoCurrentPriceItems(
        platform_store_id=fallback_platform_store_id, business_day=business_day, rows=parsed,
        response_code=code or 0, source_sha256=hashlib.sha256(raw or b"").hexdigest(), source_bytes=len(raw or b""),
    )


def _find_items(payload: Any) -> list[Any] | None:
    if not isinstance(payload, dict):
        raise TaobaoCurrentPricePayloadError("Taobao current-price response must be a JSON object.")
    values: list[Any] = [payload]
    data = payload.get("data")
    if isinstance(data, dict):
        values.append(data)
        model = data.get("model")
        if isinstance(model, dict):
            values.append(model)
    for value in values:
        for key in ("items", "itemList", "data", "list"):
            rows = value.get(key) if isinstance(value, dict) else None
            if isinstance(rows, list):
                return rows
    return [] if _response_code(payload) == 0 else None


def _response_code(payload: dict[str, Any]) -> int | None:
    data = payload.get("data")
    if isinstance(data, dict) and data.get("success") is False:
        return 1
    value = payload.get("retCode", payload.get("code"))
    if value is None:
        if isinstance(data, dict):
            value = data.get("code")
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None


def _parse_row(row: dict[str, Any]) -> TaobaoCurrentPriceItemRow:
    item_id = _text(row.get("itemId"))
    if not item_id:
        raise TaobaoCurrentPricePayloadError("A current-price row has no itemId.")
    return TaobaoCurrentPriceItemRow(
        item_id=item_id, item_title=_text(row.get("itemTitle") or row.get("itemName")) or "",
        attention=_text(row.get("attention")) or "", risk_tag=_text(row.get("riskTag")) or "",
        normal_promotion_details=_text(row.get("normalPredictPromDetails")) or "",
        predicted_promotion_details=_text(row.get("predictPromDetails")) or "",
        risk_promotion_details=_text(row.get("riskPromDetails")) or "",
        item_detail_url=_text(row.get("itemDetailUrl")) or "", main_picture=_text(row.get("mainPicture")) or "",
        low_price=_money(row.get("lowPrice")), low_price_lower_bound=_money(row.get("lowPriceLowerBound")),
        low_price_upper_bound=_money(row.get("lowPriceUpperBound")), original_price_lower_bound=_money(row.get("originalPriceLowerBound")),
        original_price_upper_bound=_money(row.get("originalPriceUpperBound")), normal_predict_price_lower_bound=_money(row.get("normalPredictPriceLowerBound")),
        normal_predict_price_upper_bound=_money(row.get("normalPredictPriceUpperBound")), predict_price_lower_bound=_money(row.get("predictPriceLowerBound")),
        predict_price_upper_bound=_money(row.get("predictPriceUpperBound")), sku_count=_decimal(row.get("skuNum")),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    value = str(value).strip()
    return value or None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _money(value: Any) -> Decimal | None:
    value = _decimal(value)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if value is not None else None
