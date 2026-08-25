from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "mtop.hd.marketing.seller.home"
PARSER_VERSION = "mtop-taojinbi-v1"
MONEY_QUANTUM = Decimal("0.01")

TAOJINBI_METRIC_CODES = (
    "coinAmount",
    "tt_ord_cnt",
    "active_user_odr_cnt",
    "tt_ord_amt",
    "coin_tt_disc_amt",
    "coin_odr_cnt",
    "coin_disc_ord_cnt",
    "coin_ord_amt",
    "coin_disc_ord_amt",
    "coin_visit_uv",
    "coin_item_visit_uv",
    "coin_item_visit_pv",
    "coin_sub_ord_cnt",
    "coin_sub_ord_amt",
    "coin_seller_inc",
    "coin_seller_exp",
    "fans_shop_vst_cnt",
    "fans_item_view_cnt",
    "fans_live_view_cnt",
    "fans_inc_cnt_cnt",
    "tgt_shop_vst_cnt",
    "tgt_live_vst_cnt",
    "spt_shop_jump",
    "coin_sub_benefit_amt",
    "tab3_expose_pv",
    "brand_box_expose_pv",
)

MONEY_CODES = {
    "tt_ord_amt",
    "coin_tt_disc_amt",
    "coin_ord_amt",
    "coin_disc_ord_amt",
    "coin_sub_ord_amt",
    "coin_sub_benefit_amt",
}


class MtopTaojinbiPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedMtopTaojinbi:
    platform_store_id: str
    business_day: date
    section: str
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
) -> ParsedMtopTaojinbi:
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
) -> ParsedMtopTaojinbi:
    _validate_mtop_success(payload)
    data = payload.get("data")
    model = data.get("model") if isinstance(data, dict) else None
    model_data = model.get("data") if isinstance(model, dict) else None
    if not isinstance(model_data, dict):
        raise MtopTaojinbiPayloadError("The MTop Taojinbi response has no model data.")

    metrics = {code: None for code in TAOJINBI_METRIC_CODES}
    section = ""
    general = model_data.get("shopGeneralInfo")
    detailed = model_data.get("shopDetailedInfo")
    if isinstance(general, dict):
        section = "general"
        general_data = general.get("generalData")
        if isinstance(general_data, dict):
            metrics["coinAmount"] = _as_decimal(general_data.get("coinAmount"))
            _read_metric_items(metrics, general_data.get("generalData"))
    elif isinstance(detailed, dict):
        section = "detailed"
        cards = detailed.get("detailedCardData")
        if isinstance(cards, dict):
            _read_metric_items(metrics, cards.get("detailedCardData"))
    else:
        raise MtopTaojinbiPayloadError(
            "The MTop Taojinbi response has neither general nor detailed data."
        )

    for code in MONEY_CODES:
        value = metrics.get(code)
        if value is not None:
            metrics[code] = value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedMtopTaojinbi(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        section=section,
        metrics=metrics,
        response_code=0,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=f"{ENDPOINT_KEY}.{section}",
        parser_version=PARSER_VERSION,
    )


def _read_metric_items(
    metrics: dict[str, Decimal | None],
    items: object,
) -> None:
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("metricCode") or "")
        if code not in metrics:
            continue
        metrics[code] = _as_decimal(item.get("metricStringValue"))


def _validate_mtop_success(payload: dict[str, Any]) -> None:
    ret = payload.get("ret")
    if not isinstance(ret, list) or not any(str(item).startswith("SUCCESS::") for item in ret):
        raise MtopTaojinbiPayloadError(f"MTop Taojinbi request failed: {ret}")


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None
