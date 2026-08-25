from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "alimama.cps.data_home_overview"
PARSER_VERSION = "alimama-cps-overview-v1"


class CpsPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedCpsOverview:
    platform_store_id: str
    business_day: date
    payment_commission_expense: Decimal | None
    payment_service_fee_expense: Decimal | None
    payment_commission_rate: Decimal | None
    payment_service_fee_rate: Decimal | None
    payment_order_count: Decimal | None
    payment_amount: Decimal | None
    click_visitors: Decimal | None
    settlement_total_expense: Decimal | None
    settlement_order_count: Decimal | None
    settlement_amount: Decimal | None
    preorder_deposit_order_count: Decimal | None
    preorder_deposit_amount: Decimal | None
    preorder_remaining_amount: Decimal | None
    preorder_total_amount: Decimal | None
    payment_marketing_service_fee_expense: Decimal | None
    settlement_marketing_service_fee_expense: Decimal | None
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
                self.payment_commission_expense,
                self.payment_service_fee_expense,
                self.payment_commission_rate,
                self.payment_service_fee_rate,
                self.payment_order_count,
                self.payment_amount,
                self.click_visitors,
                self.settlement_total_expense,
                self.settlement_order_count,
                self.settlement_amount,
                self.preorder_deposit_order_count,
                self.preorder_deposit_amount,
                self.preorder_remaining_amount,
                self.preorder_total_amount,
                self.payment_marketing_service_fee_expense,
                self.settlement_marketing_service_fee_expense,
            )
        )


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedCpsOverview:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise CpsPayloadError("The CPS overview response must be a JSON object.")
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
) -> ParsedCpsOverview:
    result = _result_row(payload)
    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedCpsOverview(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        payment_commission_expense=_metric_decimal(result, "pay_ord_cfee_8"),
        payment_service_fee_expense=_metric_decimal(result, "pay_ord_sfee_8"),
        payment_commission_rate=_metric_decimal(result, "pay_ord_cfee_rt_8"),
        payment_service_fee_rate=_metric_decimal(result, "pay_ser_ord_sfee_rt_8"),
        payment_order_count=_metric_decimal(result, "pay_ord_num_8"),
        payment_amount=_metric_decimal(result, "pay_ord_amt_8"),
        click_visitors=_metric_decimal(result, "uclk_uv_8"),
        settlement_total_expense=_metric_decimal(result, "sett_ord_total_fee_8"),
        settlement_order_count=_metric_decimal(result, "sett_ord_num_8"),
        settlement_amount=_metric_decimal(result, "sett_ord_amt_8"),
        preorder_deposit_order_count=_metric_decimal(result, "dep_ord_num_8"),
        preorder_deposit_amount=_metric_decimal(result, "dep_ord_dep_amt_8"),
        preorder_remaining_amount=_metric_decimal(result, "dep_ord_rest_amt_8"),
        preorder_total_amount=_metric_decimal(result, "dep_ord_total_amt_8"),
        payment_marketing_service_fee_expense=_metric_decimal(result, "pay_bmkt_fee_8"),
        settlement_marketing_service_fee_expense=_metric_decimal(result, "sett_bmkt_fee_8"),
        response_code=_response_code(payload),
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _result_row(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    if isinstance(result, dict):
        return result
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
        return result[0]
    raise CpsPayloadError("The CPS overview response has no data.result object.")


def _response_code(payload: dict[str, Any]) -> int:
    data = payload.get("data")
    for candidate in (
        payload.get("resultCode"),
        payload.get("code"),
        data.get("code") if isinstance(data, dict) else None,
    ):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return 0


def _metric_decimal(row: dict[str, Any], field: str) -> Decimal | None:
    value = row.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
