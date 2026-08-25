from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "sycm.csp.user.sale.summary.list"
PARSER_VERSION = "sycm-customer-service-accounts-v1"

NICKNAME_ALIASES = (
    "nick",
    "nickName",
    "userNick",
    "accountNick",
    "accountName",
    "psnNickName",
    "wwNick",
    "serviceNick",
    "userName",
)
METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "consult_users": (
        "cstUv1d",
        "cstUv",
        "consultUv1d",
        "consultCnt",
        "consultUserCnt",
    ),
    "valid_reception_users": (
        "validReplyUv1d",
        "validReplyUv",
        "validReplyCnt",
    ),
    "consult_order_users": (
        "cstOrdUv1d",
        "wwConsultOrdByrCnt",
        "consultOrdByrCnt",
        "finalCstUv",
    ),
    "order_users": (
        "ordCrtUv1d",
        "ordUsrCnt1d",
        "ordCrtUv",
        "orderUv",
        "crtOrdByrCnt",
    ),
    "order_amount": (
        "crtAmt1d",
        "ordAmt1d",
        "crtVldAmt1d",
        "crtOrdAmt",
        "orderAmt",
        "csCrtOrdAmt",
    ),
    "sale_users": (
        "payUsrCnt1d",
        "customerServiceSaleCnt",
        "payByrCnt1d",
    ),
    "sale_amount": (
        "payAmt1d",
        "customerServiceGmv",
    ),
    "sale_quantity": (
        "payItmCnt1d",
        "payQty1d",
        "payOrdItmQty1d",
        "saleQty1d",
    ),
    "order_count": (
        "payOrdCnt1d",
        "payMordCnt1d",
        "payCnt1d",
        "orderCnt1d",
        "saleOrdCnt1d",
    ),
    "sale_amount_ratio": ("proportionCss",),
    "refund_amount": (
        "sucRefundAmt",
        "sucRefundAmount",
        "rfdAmt1d",
        "csRfdSucAmt",
    ),
    "net_sale_amount": (
        "netPayAmt",
        "realPayAmt1d",
        "csNetPayAmt",
    ),
}
ALL_ROW_ALIASES = {
    *NICKNAME_ALIASES,
    *(
        alias
        for aliases in METRIC_ALIASES.values()
        for alias in aliases
    ),
}
SUMMARY_NICKNAMES = {"汇总值", "汇总", "合计", "总计"}


class SycmCustomerServiceAccountsPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedCustomerServiceAccountRow:
    nickname: str
    consult_users: Decimal | None
    valid_reception_users: Decimal | None
    consult_order_users: Decimal | None
    order_users: Decimal | None
    order_amount: Decimal | None
    sale_users: Decimal | None
    sale_amount: Decimal | None
    sale_quantity: Decimal | None
    order_count: Decimal | None
    sale_amount_ratio: Decimal | None
    refund_amount: Decimal | None
    net_sale_amount: Decimal | None


@dataclass(frozen=True)
class ParsedSycmCustomerServiceAccounts:
    platform_store_id: str
    business_day: date
    rows: list[ParsedCustomerServiceAccountRow]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str

    @property
    def metric_count(self) -> int:
        return len(self.rows)


def load_and_parse(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmCustomerServiceAccounts:
    raw = path.read_bytes()
    payload = _load_json_or_jsonp(raw)
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
) -> ParsedSycmCustomerServiceAccounts:
    response_code = _validate_success(payload)
    source_rows = _find_account_rows(payload)
    rows_by_nickname: dict[str, ParsedCustomerServiceAccountRow] = {}
    for item in source_rows:
        nickname = _first_text(item, NICKNAME_ALIASES)
        if not nickname or nickname.strip() in SUMMARY_NICKNAMES:
            continue
        rows_by_nickname[nickname] = ParsedCustomerServiceAccountRow(
            nickname=nickname,
            consult_users=_metric_decimal(item, METRIC_ALIASES["consult_users"]),
            valid_reception_users=_metric_decimal(
                item,
                METRIC_ALIASES["valid_reception_users"],
            ),
            consult_order_users=_metric_decimal(
                item,
                METRIC_ALIASES["consult_order_users"],
            ),
            order_users=_metric_decimal(item, METRIC_ALIASES["order_users"]),
            order_amount=_metric_decimal(item, METRIC_ALIASES["order_amount"]),
            sale_users=_metric_decimal(item, METRIC_ALIASES["sale_users"]),
            sale_amount=_metric_decimal(item, METRIC_ALIASES["sale_amount"]),
            sale_quantity=_metric_decimal(item, METRIC_ALIASES["sale_quantity"]),
            order_count=_metric_decimal(item, METRIC_ALIASES["order_count"]),
            sale_amount_ratio=_metric_decimal(
                item,
                METRIC_ALIASES["sale_amount_ratio"],
            ),
            refund_amount=_metric_decimal(item, METRIC_ALIASES["refund_amount"]),
            net_sale_amount=_metric_decimal(
                item,
                METRIC_ALIASES["net_sale_amount"],
            ),
        )

    platform_store_id = (
        _recursive_find_text(
            payload,
            ("sellerId", "shopId", "mainUserId", "runAsUserId", "userId"),
        )
        or fallback_platform_store_id
    )
    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmCustomerServiceAccounts(
        platform_store_id=platform_store_id,
        business_day=business_day,
        rows=list(rows_by_nickname.values()),
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _load_json_or_jsonp(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8-sig").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.match(r"^[^(]+\((.*)\)\s*;?\s*$", text, flags=re.DOTALL)
        if match is None:
            raise SycmCustomerServiceAccountsPayloadError(
                "The saved customer-service account response is neither JSON nor JSONP."
            )
        payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise SycmCustomerServiceAccountsPayloadError(
            "The saved customer-service account response root is not an object."
        )
    return payload


def _validate_success(payload: dict[str, Any]) -> int:
    code = _as_int(payload.get("code"))
    if code not in (0, 200):
        message = payload.get("message") or payload.get("msg") or "unknown response error"
        raise SycmCustomerServiceAccountsPayloadError(
            f"SYCM customer-service account response failed: {message}"
        )
    if payload.get("success") is False:
        message = payload.get("message") or payload.get("msg") or "unknown response error"
        raise SycmCustomerServiceAccountsPayloadError(
            f"SYCM customer-service account response failed: {message}"
        )
    return code


def _find_account_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[tuple[int, list[dict[str, Any]]]] = []
    found_known_empty_list = False

    def walk(node: object) -> None:
        nonlocal found_known_empty_list
        if isinstance(node, list):
            dict_rows = [item for item in node if isinstance(item, dict)]
            if dict_rows:
                score = sum(
                    sum(key in ALL_ROW_ALIASES for key in row)
                    for row in dict_rows
                )
                if score:
                    candidates.append((score, dict_rows))
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for key in ("data", "list", "records", "result", "rows", "items"):
                value = node.get(key)
                if isinstance(value, list) and not value:
                    found_known_empty_list = True
                if isinstance(value, (dict, list)):
                    walk(value)
            for key, value in node.items():
                if key not in {"data", "list", "records", "result", "rows", "items"}:
                    if isinstance(value, (dict, list)):
                        walk(value)

    walk(payload)
    if not candidates:
        if found_known_empty_list:
            return []
        raise SycmCustomerServiceAccountsPayloadError(
            "The customer-service account response has no recognized account row list."
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _metric_decimal(
    row: dict[str, Any],
    aliases: tuple[str, ...],
) -> Decimal | None:
    for alias in aliases:
        if alias in row:
            return _as_decimal(_extract_scalar(row.get(alias)))
    return None


def _first_text(row: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        if alias not in row:
            continue
        value = _extract_scalar(row.get(alias))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _extract_scalar(value: object) -> object:
    if isinstance(value, dict):
        for key in (
            "value",
            "absolute",
            "metricValue",
            "metricStringValue",
            "name",
            "nick",
            "text",
        ):
            if key in value:
                extracted = _extract_scalar(value.get(key))
                if extracted is not None:
                    return extracted
        return None
    if isinstance(value, list):
        for item in value:
            extracted = _extract_scalar(item)
            if extracted is not None:
                return extracted
        return None
    return value


def _recursive_find_text(node: object, keys: tuple[str, ...]) -> str:
    if isinstance(node, dict):
        for key in keys:
            if key not in node:
                continue
            value = _extract_scalar(node.get(key))
            if value is not None and str(value).strip():
                return str(value).strip()
        for value in node.values():
            found = _recursive_find_text(value, keys)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _recursive_find_text(item, keys)
            if found:
                return found
    return ""


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result / Decimal("100") if is_percent else result


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
