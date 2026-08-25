from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_PLATFORM_STORE_ID = "2200573698992"
ENDPOINT_KEY = "sale.taobao.domain.item.query"
PARSER_VERSION = "taobao-activity-item-snapshots-v1"


class TaobaoActivityItemPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class TaobaoActivityItemSnapshotRow:
    snapshot_type: str
    marketing_id: str
    item_id: str
    item_name: str
    status: str
    status_name: str
    activity_name: str
    start_time: str
    end_time: str
    sign_time: str
    item_link: str
    activity_url: str
    item_picture: str
    activity_price_name: str
    supply_price_name: str
    common_activity_tags: str
    material_status_name: str
    ic_status_name: str
    original_price: Decimal | None
    activity_price: Decimal | None
    supply_price: Decimal | None
    inventory: Decimal | None
    sold_count: Decimal | None
    limit_count: Decimal | None
    signed_count: Decimal | None
    unsigned_count: Decimal | None

    @property
    def metric_count(self) -> int:
        return sum(value is not None for value in (
            self.original_price, self.activity_price, self.supply_price, self.inventory,
            self.sold_count, self.limit_count, self.signed_count, self.unsigned_count,
        ))


@dataclass(frozen=True)
class ParsedTaobaoActivityItemSnapshots:
    platform_store_id: str
    business_day: date
    rows: list[TaobaoActivityItemSnapshotRow]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str = ENDPOINT_KEY
    parser_version: str = PARSER_VERSION

    @property
    def metric_count(self) -> int:
        return sum(row.metric_count for row in self.rows)


def load_and_parse(path: Path, business_day: date, fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID) -> ParsedTaobaoActivityItemSnapshots:
    raw = path.read_bytes()
    return parse_payload(json.loads(raw.decode("utf-8")), business_day=business_day, raw=raw, fallback_platform_store_id=fallback_platform_store_id)


def parse_payload(payload: dict[str, Any], *, business_day: date, raw: bytes | None = None, fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID) -> ParsedTaobaoActivityItemSnapshots:
    if not isinstance(payload, dict):
        raise TaobaoActivityItemPayloadError("Taobao activity response must be a JSON object.")
    snapshots = payload.get("snapshots") if isinstance(payload, dict) else None
    source_snapshots = snapshots if isinstance(snapshots, list) else [payload]
    rows: list[TaobaoActivityItemSnapshotRow] = []
    for snapshot in source_snapshots:
        if not isinstance(snapshot, dict):
            continue
        pages = snapshot.get("pages")
        source_pages = pages if isinstance(pages, list) else [snapshot]
        snapshot_type = str(snapshot.get("snapshotType") or snapshot.get("snapshot_type") or "").strip()
        if snapshot_type not in {"bybt_online", "bybt_pending", "flash_sale_online"}:
            raise TaobaoActivityItemPayloadError("snapshotType must be bybt_online, bybt_pending, or flash_sale_online.")
        for page in source_pages:
            if not isinstance(page, dict):
                continue
            code = _response_code(page)
            if code not in (0, None):
                raise TaobaoActivityItemPayloadError(f"Taobao activity response failed: code={code}")
            source_rows = _find_rows(page)
            if source_rows is None:
                raise TaobaoActivityItemPayloadError("Taobao activity response has no data list.")
            rows.extend(_parse_row(row, snapshot_type) for row in source_rows if isinstance(row, dict))
    rows = list({(row.snapshot_type, row.item_id, row.marketing_id): row for row in rows}.values())
    return ParsedTaobaoActivityItemSnapshots(
        platform_store_id=fallback_platform_store_id, business_day=business_day, rows=rows,
        response_code=code or 0, source_sha256=hashlib.sha256(raw or b"").hexdigest(), source_bytes=len(raw or b""),
    )


def _find_rows(payload: dict[str, Any]) -> list[Any] | None:
    data = payload.get("data")
    if isinstance(data, dict):
        rows = data.get("data")
        if isinstance(rows, list):
            return rows
    if isinstance(data, list):
        return data
    return [] if _response_code(payload) == 0 else None


def _response_code(payload: dict[str, Any]) -> int | None:
    if payload.get("success") is False:
        return 1
    value = payload.get("code")
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None


def _parse_row(row: dict[str, Any], snapshot_type: str) -> TaobaoActivityItemSnapshotRow:
    item_id = _text(row.get("itemId") or _nested(row, "themisInfo.parentIdMap.icItem"))
    if not item_id:
        raise TaobaoActivityItemPayloadError("A Taobao activity row has no itemId.")
    return TaobaoActivityItemSnapshotRow(
        snapshot_type=snapshot_type, marketing_id=_text(row.get("juId") or _nested(row, "themisInfo.domainId")) or "",
        item_id=item_id, item_name=_text(row.get("itemName")) or "", status=_text(row.get("status")) or "",
        status_name=_text(row.get("statusName")) or "", activity_name=_text(row.get("activityName")) or "",
        start_time=_time(row.get("onlineStartTime")), end_time=_time(row.get("onlineEndTime")), sign_time=_time(row.get("signTime")),
        item_link=_text(row.get("itemLink")) or "", activity_url=_text(row.get("activityUrl")) or "", item_picture=_text(row.get("itemPic")) or "",
        activity_price_name=_text(row.get("activityPriceName")) or "", supply_price_name=_text(row.get("supplyPriceName")) or "",
        common_activity_tags=_text(row.get("commonActivityTags")) or "", material_status_name=_text(row.get("materialStatusName")) or "",
        ic_status_name=_text(row.get("icStatusName")) or "", original_price=_money(row.get("originalPrice")), activity_price=_money(row.get("activityPrice")),
        supply_price=_money(row.get("supplyPrice")), inventory=_decimal(row.get("inventory")), sold_count=_decimal(row.get("soldCount")),
        limit_count=_decimal(row.get("limitNum")), signed_count=_decimal(_nested(row, "playSignInfo.signedCount")), unsigned_count=_decimal(_nested(row, "playSignInfo.unsignedCount")),
    )


def _nested(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


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


def _time(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        millis = int(value)
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat(sep=" ")
    except (TypeError, ValueError, OverflowError):
        return _text(value) or ""
