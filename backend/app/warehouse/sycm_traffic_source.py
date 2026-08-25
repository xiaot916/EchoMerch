from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any


class SycmTrafficSourcePayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTrafficSourceRow:
    row_order: int
    level1: str
    level2: str
    level3: str
    source_level: int
    source_path: str
    visitors: Decimal
    new_visitors: Decimal
    cart_buyers: Decimal
    product_favorite_buyers: Decimal
    paid_buyers: Decimal
    conversion_rate: Decimal
    paid_amount: Decimal
    paid_amount_share: Decimal
    uv_value: Decimal
    order_buyers: Decimal
    order_amount: Decimal
    order_conversion_rate: Decimal
    value_json: str


@dataclass(frozen=True)
class ParsedSycmTrafficSource:
    business_day: date
    rows: list[ParsedTrafficSourceRow]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str


def load_and_parse(path: Path, business_day: date) -> ParsedSycmTrafficSource:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(payload, business_day=business_day, raw=raw)


def parse_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
) -> ParsedSycmTrafficSource:
    root = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    response_code = _as_int(root.get("code"))
    if response_code != 0:
        message = root.get("message") or payload.get("message") or "unknown response error"
        raise SycmTrafficSourcePayloadError(f"SYCM traffic source response failed: {message}")

    tree = _extract_tree(root)
    rows: list[ParsedTrafficSourceRow] = []
    for item in tree:
        if not isinstance(item, dict):
            continue
        level1 = _node_name(item)
        _parse_node(item, level1, "", "", rows)

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmTrafficSource(
        business_day=business_day,
        rows=rows,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key="sycm.flow.v5.shop.source.tree.v4",
        parser_version="sycm-traffic-source-v1",
    )


def _extract_tree(root: dict[str, Any]) -> list[Any]:
    data = root.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, list):
            return nested
        rows = data.get("list")
        if isinstance(rows, list):
            return rows
    raise SycmTrafficSourcePayloadError("The SYCM traffic source response has no tree data.")


def _parse_node(
    node: dict[str, Any],
    level1: str,
    level2: str,
    level3: str,
    rows: list[ParsedTrafficSourceRow],
) -> None:
    if level1:
        source_level = 3 if level3 else 2 if level2 else 1
        rows.append(
            ParsedTrafficSourceRow(
                row_order=len(rows) + 1,
                level1=level1,
                level2=level2,
                level3=level3,
                source_level=source_level,
                source_path=" / ".join(part for part in (level1, level2, level3) if part),
                visitors=_metric_decimal(node, "uv"),
                new_visitors=_metric_decimal(node, "newUv"),
                cart_buyers=_metric_decimal(node, "cartByrCnt"),
                product_favorite_buyers=_metric_decimal(node, "cltItmCnt"),
                paid_buyers=_metric_decimal(node, "payByrCnt"),
                conversion_rate=_metric_decimal(node, "payRate"),
                paid_amount=_metric_decimal(node, "payAmt"),
                paid_amount_share=_metric_decimal(node, "payPct"),
                uv_value=_metric_decimal(node, "uvValue"),
                order_buyers=_metric_decimal(node, "crtByrCnt"),
                order_amount=_metric_decimal(node, "crtVldAmt"),
                order_conversion_rate=_metric_decimal(node, "crtRate"),
                value_json=_node_value_json(node),
            )
        )

    children = node.get("children")
    if not isinstance(children, list):
        return

    for child in children:
        if not isinstance(child, dict):
            continue
        child_name = _node_name(child)
        if level1 == "付费推广" and level2 == "无界":
            _parse_node(child, level1, level2, child_name, rows)
        elif level1 and not level2:
            _parse_node(child, level1, child_name, "", rows)
        else:
            _parse_node(child, level1, level2, level3, rows)


def _node_name(node: dict[str, Any]) -> str:
    return _value_as_text(node.get("pageName"))


def _node_value_json(node: dict[str, Any]) -> str:
    shallow = {
        key: _self_only_value(value)
        for key, value in node.items()
        if key != "children" and not key.startswith("rival")
    }
    return json.dumps(
        shallow,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _self_only_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _self_only_value(child)
            for key, child in value.items()
            if not key.startswith("rival")
        }
    if isinstance(value, list):
        return [_self_only_value(item) for item in value]
    return value


def _metric_decimal(node: dict[str, Any], code: str) -> Decimal:
    return _as_decimal(_value(node.get(code))) or Decimal("0")


def _value(entry: object) -> object:
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def _value_as_text(entry: object) -> str:
    value = _value(entry)
    return "" if value is None else str(value)


def _as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace('"', "").replace(",", "")
        if not value or value == "-":
            return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
