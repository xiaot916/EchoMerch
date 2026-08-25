from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "mtop.taobao.argus.GetRiskDetectListInfo"
PARSER_VERSION = "taobao-risk-price-items-v1"


class TaobaoRiskPricePayloadError(ValueError):
    pass


@dataclass(frozen=True)
class TaobaoRiskPriceItemRow:
    item_id: str
    item_name: str
    modified_at: str
    risk_type: str
    risk_description: str
    promotion_details: str
    risk_sub_description: str
    low_price: Decimal | None
    original_price: Decimal | None
    low_price_sku_count: Decimal | None

    @property
    def metric_count(self) -> int:
        return sum(value is not None for value in (self.low_price, self.original_price, self.low_price_sku_count))


@dataclass(frozen=True)
class ParsedTaobaoRiskPriceItems:
    platform_store_id: str
    business_day: date
    rows: list[TaobaoRiskPriceItemRow]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return sum(row.metric_count for row in self.rows)


def load_and_parse(path: Path, business_day: date, fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID) -> ParsedTaobaoRiskPriceItems:
    raw = path.read_bytes()
    return parse_payload(json.loads(raw.decode("utf-8")), business_day=business_day, raw=raw, fallback_platform_store_id=fallback_platform_store_id)


def parse_payload(payload: dict[str, Any], *, business_day: date, raw: bytes | None = None, fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID) -> ParsedTaobaoRiskPriceItems:
    pages = payload.get("pages") if isinstance(payload, dict) else None
    source_pages = pages if isinstance(pages, list) else [payload]
    parsed: list[TaobaoRiskPriceItemRow] = []
    code = 0
    for page in source_pages:
        if not isinstance(page, dict):
            continue
        rows = _find_records(page)
        if rows is None:
            raise TaobaoRiskPricePayloadError("Taobao risk-price response has no riskDetectRecords list.")
        page_code = _response_code(page)
        if page_code not in (0, 200, None):
            raise TaobaoRiskPricePayloadError(f"Taobao risk-price response failed: code={page_code}")
        parsed.extend(_parse_row(row) for row in rows if isinstance(row, dict))
    parsed = list({row.item_id: row for row in parsed}.values())
    return ParsedTaobaoRiskPriceItems(
        platform_store_id=fallback_platform_store_id, business_day=business_day, rows=parsed,
        response_code=code, source_sha256=hashlib.sha256(raw or b"").hexdigest(), source_bytes=len(raw or b""),
    )


def _find_records(payload: Any) -> list[Any] | None:
    if not isinstance(payload, dict):
        raise TaobaoRiskPricePayloadError("Taobao risk-price response must be a JSON object.")
    candidates = [payload]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.append(data)
        model = data.get("model")
        if isinstance(model, dict):
            candidates.append(model)
    for value in candidates:
        for key in ("riskDetectRecords", "records", "items", "data"):
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


def _parse_row(row: dict[str, Any]) -> TaobaoRiskPriceItemRow:
    item = row.get("itemInfo") if isinstance(row.get("itemInfo"), dict) else {}
    risk = row.get("riskDesc") if isinstance(row.get("riskDesc"), dict) else {}
    item_id = _text(item.get("itemId") or row.get("itemId"))
    if not item_id:
        raise TaobaoRiskPricePayloadError("A risk-price row has no itemId.")
    return TaobaoRiskPriceItemRow(
        item_id=item_id, item_name=_text(item.get("itemTitle") or row.get("itemTitle")) or "",
        modified_at=_text(row.get("gmtModified") or row.get("gmtModifiedTime")) or "",
        risk_type=_text(row.get("riskType") or row.get("riskCode")) or "ITEM_PREDICT_RISK_DETECT",
        risk_description=_text(risk.get("riskDesc") or risk.get("description") or row.get("riskDesc")) or "",
        promotion_details=_text(risk.get("promotionDetails") or risk.get("promotionDetail")) or "",
        risk_sub_description=_text(risk.get("riskDetectSubDesc") or risk.get("subDesc")) or "",
        low_price=_money(risk.get("exampleLowPrice") or risk.get("lowPrice")),
        original_price=_money(item.get("originalPrice") or row.get("originalPrice")),
        low_price_sku_count=_decimal(risk.get("lowPriceSkuNum") or risk.get("skuNum")),
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
