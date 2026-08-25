from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.local_database import (
    UTRY_REPURCHASE_METRICS,
    UTRY_SAMPLE_METRICS,
)


SAMPLE_ENDPOINT_KEY = "quark.utry.sample_platform.sample_overview"
REPURCHASE_ENDPOINT_KEY = "quark.utry.sample_platform.repurchase_overview"
PARSER_VERSION = "utry-overviews-v1"


class UtryPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class UtrySampleRow:
    product_id: str
    product_name: str
    leaf_category_name: str
    industry_group_name: str
    first_category_name: str
    second_category_name: str
    metrics: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class UtryRepurchaseRow:
    product_id: str
    product_name: str
    ju_id: str
    leaf_category: str
    industry_group: str
    first_category: str
    second_category: str
    bind_regular_product: str
    configured_repurchase_coupon: str
    configured_repurchase_gift: str
    metrics: tuple[Decimal | None, ...]


@dataclass(frozen=True)
class ParsedUtrySampleReport:
    platform_store_id: str
    business_day: date
    rows: tuple[UtrySampleRow, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = SAMPLE_ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return len(self.rows) * len(UTRY_SAMPLE_METRICS)


@dataclass(frozen=True)
class ParsedUtryRepurchaseReport:
    platform_store_id: str
    business_day: date
    rows: tuple[UtryRepurchaseRow, ...]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = REPURCHASE_ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return len(self.rows) * len(UTRY_REPURCHASE_METRICS)


_SAMPLE_FIELDS = (
    "商品ID",
    "商品标题",
    "叶子类目名称",
    "行业大组名称",
    "一级大类名称",
    "二级大类名称",
    *UTRY_SAMPLE_METRICS,
)
_REPURCHASE_FIELDS = (
    "商品ID",
    "商品名称",
    "ju_id",
    "叶子类目",
    "行业大组",
    "一级大类",
    "二级大类",
    *UTRY_REPURCHASE_METRICS,
    "是否绑定正装1/0",
    "是否配置回购券1/0",
    "是否配置回购礼金1/0",
)


def load_and_parse_sample(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedUtrySampleReport:
    raw, payload = _load(path)
    return parse_sample_payload(
        payload,
        business_day=business_day,
        raw=raw,
        fallback_platform_store_id=fallback_platform_store_id,
    )


def load_and_parse_repurchase(
    path: Path,
    business_day: date,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedUtryRepurchaseReport:
    raw, payload = _load(path)
    return parse_repurchase_payload(
        payload,
        business_day=business_day,
        raw=raw,
        fallback_platform_store_id=fallback_platform_store_id,
    )


def parse_sample_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedUtrySampleReport:
    rows = _rows(
        payload,
        _SAMPLE_FIELDS,
        aliases={
            "商品标题": ("商品名称",),
            "叶子类目名称": ("叶子类目",),
            "行业大组名称": ("行业大组",),
            "一级大类名称": ("一级大类",),
            "二级大类名称": ("二级大类",),
            "入仓单量": ("入仓派样单量",),
        },
        required_fields=("商品ID",),
    )
    parsed: dict[str, UtrySampleRow] = {}
    for row in rows:
        product_id = _text(row.get("商品ID"))
        if not product_id:
            continue
        parsed[product_id] = UtrySampleRow(
            product_id=product_id,
            product_name=_text(row.get("商品标题") or row.get("商品名称")),
            leaf_category_name=_text(row.get("叶子类目名称")),
            industry_group_name=_text(row.get("行业大组名称")),
            first_category_name=_text(row.get("一级大类名称")),
            second_category_name=_text(row.get("二级大类名称")),
            metrics=tuple(_decimal(row.get(field)) for field in UTRY_SAMPLE_METRICS),
        )
    return ParsedUtrySampleReport(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=tuple(parsed.values()),
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
    )


def parse_repurchase_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
    fallback_platform_store_id: str = "2200573698992",
) -> ParsedUtryRepurchaseReport:
    rows = _rows(
        payload,
        _REPURCHASE_FIELDS,
        aliases={
            "同店30日回购UV": ("同店30日回购uv",),
            "同店90日回购UV": ("同店90日回购uv",),
            "同店365日回购UV": ("同店365日回购uv",),
            "同品牌30日回购UV": ("同品牌30日回购uv",),
            "同品牌90日回购UV": ("同品牌90日回购uv",),
            "同品牌365日回购UV": ("同品牌365日回购uv",),
        },
        required_fields=("商品ID",),
    )
    parsed: dict[str, UtryRepurchaseRow] = {}
    for row in rows:
        product_id = _text(row.get("商品ID"))
        if not product_id:
            continue
        parsed[product_id] = UtryRepurchaseRow(
            product_id=product_id,
            product_name=_text(row.get("商品名称")),
            ju_id=_text(row.get("ju_id")),
            leaf_category=_text(row.get("叶子类目")),
            industry_group=_text(row.get("行业大组")),
            first_category=_text(row.get("一级大类")),
            second_category=_text(row.get("二级大类")),
            bind_regular_product=_text(row.get("是否绑定正装1/0")),
            configured_repurchase_coupon=_text(row.get("是否配置回购券1/0")),
            configured_repurchase_gift=_text(row.get("是否配置回购礼金1/0")),
            metrics=tuple(_decimal(row.get(field)) for field in UTRY_REPURCHASE_METRICS),
        )
    return ParsedUtryRepurchaseReport(
        platform_store_id=fallback_platform_store_id,
        business_day=business_day,
        rows=tuple(parsed.values()),
        response_code=0,
        source_sha256=hashlib.sha256(raw or b"").hexdigest(),
        source_bytes=len(raw) if raw is not None else 0,
    )


def _load(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UtryPayloadError("The U先 response is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise UtryPayloadError("The U先 response must be an object.")
    return raw, payload


def _rows(
    payload: dict[str, Any],
    expected_fields: tuple[str, ...],
    aliases: dict[str, tuple[str, ...]] | None = None,
    required_fields: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    if payload.get("code") not in (0, "0") or payload.get("success") is False:
        raise UtryPayloadError(
            f"The U先 response failed: {payload.get('message') or payload.get('finalMessage') or payload.get('code')}"
        )
    data = payload.get("data")
    value = data.get("value") if isinstance(data, dict) else None
    if not isinstance(value, dict):
        raise UtryPayloadError("The U先 response has no data.value.")
    columns = value.get("columns")
    values = value.get("values")
    if not isinstance(columns, list) or not isinstance(values, list):
        raise UtryPayloadError("The U先 response has no columns or values.")
    labels: list[str] = []
    for column in columns:
        try:
            label = column["cells"][0]["props"]["label"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UtryPayloadError("The U先 response contains an invalid column definition.") from exc
        labels.append(str(label).strip())
    alias_map = aliases or {}
    normalized_labels = {label.casefold(): label for label in labels}
    missing = [
        field
        for field in (required_fields or expected_fields)
        if field.casefold() not in normalized_labels
        and not any(alias.casefold() in normalized_labels for alias in alias_map.get(field, ()))
    ]
    if missing:
        raise UtryPayloadError("The U先 response is missing fields: " + ", ".join(missing))
    resolved = {}
    positions = {label.casefold(): index for index, label in enumerate(labels)}
    for field in expected_fields:
        if field.casefold() in positions:
            resolved[field] = positions[field.casefold()]
            continue
        resolved[field] = next(
            (positions[alias.casefold()] for alias in alias_map.get(field, ()) if alias.casefold() in positions),
            None,
        )
    result: list[dict[str, Any]] = []
    for raw_row in values:
        if not isinstance(raw_row, list):
            continue
        result.append(
            {
                field: _cell_value(raw_row, source_index)
                for field, source_index in resolved.items()
            }
        )
    return result


def _cell_value(row: list[Any], index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    cell = row[index]
    return cell.get("v") if isinstance(cell, dict) else cell


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
