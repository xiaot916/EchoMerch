from __future__ import annotations

"""SYCM home board (growth factor / month overview / experience scorecard) warehouse.

Parses the response files produced by ``scripts/fetch_sycm_home_board.py``
and upserts one row per store per business day into
``store_daily_sycm_home_board``.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any


ENDPOINT_KEY = "sycm.home_board.daily"
PARSER_VERSION = "sycm-home-board-v1"
METRIC_PREFIX = "home_board."

# Keys whose value is free text rather than a number. The metric list only
# carries numeric values, so these are surfaced separately on the parse result.
TEXT_METRIC_KEYS = frozenset({"cateLevel1Name"})


class HomeBoardPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedHomeBoardMetric:
    code: str
    numeric_value: Decimal | None
    value_json: str


@dataclass(frozen=True)
class ParsedHomeBoard:
    business_day: date
    metrics: list[ParsedHomeBoardMetric]
    text_values: dict[str, str]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str
    endpoint_name: str


def load_and_parse(
    path: Path,
    business_day: date,
    endpoint_name: str,
) -> ParsedHomeBoard:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(payload, business_day=business_day, raw=raw, endpoint_name=endpoint_name)


def parse_payload(
    payload: dict[str, Any],
    business_day: date,
    raw: bytes | None = None,
    endpoint_name: str = "grow_factor",
) -> ParsedHomeBoard:
    """Extract flat numeric metrics from one home-board response file.

    Handles both ``content.data`` and top-level ``data`` envelopes, skipping
    dimension / nested-structure keys that are not plain numeric values.
    """
    inner = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    code = _as_int(inner.get("code"))
    if code not in (0, None):
        message = inner.get("message") or "unknown response error"
        raise HomeBoardPayloadError(
            f"SYCM home board {endpoint_name} response failed: {message}"
        )

    data = inner.get("data") or payload.get("data")
    if not isinstance(data, dict):
        # Some endpoints return a list (e.g. trend series). Parse the first dict.
        if isinstance(data, list) and data and isinstance(data[0], dict):
            data = data[0]
        elif data is None:
            raise HomeBoardPayloadError(
                f"SYCM home board {endpoint_name} response has no data object."
            )
        else:
            raise HomeBoardPayloadError(
                f"SYCM home board {endpoint_name} data is neither dict nor list-of-dict."
            )

    metrics: list[ParsedHomeBoardMetric] = []
    text_values: dict[str, str] = {}
    for key, entry in data.items():
        if key in {"sellerId", "statDate", "statTime"}:
            continue
        value = _extract_value(entry)
        if key in TEXT_METRIC_KEYS and isinstance(value, str) and value:
            text_values[key] = value
        numeric = _as_decimal(value)
        if numeric is None:
            continue
        code_str = f"{METRIC_PREFIX}{endpoint_name}.{key}"
        value_json = json.dumps(
            {"sourceCode": key, "value": value},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        metrics.append(
            ParsedHomeBoardMetric(
                code=code_str,
                numeric_value=numeric,
                value_json=value_json,
            )
        )

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedHomeBoard(
        business_day=business_day,
        metrics=metrics,
        text_values=text_values,
        response_code=code or 0,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
        endpoint_name=endpoint_name,
    )


def _extract_value(entry: Any) -> Any:
    """Return the leaf value from a SYCM metric entry."""
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
