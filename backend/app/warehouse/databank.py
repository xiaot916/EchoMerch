from __future__ import annotations

"""Parser and idempotent writer for the daily Tmall Brand Data Bank snapshot."""

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from app.core.local_database import (
    BRAND_ASSET_DIMENSION_TABLE,
    BRAND_ASSET_METRICS_TABLE,
    BRAND_ASSET_OVERVIEW_TABLE,
    BRAND_ASSET_STAGE_TABLE,
    BRAND_ID,
    BRAND_STATISTIC_SCOPE,
    BRAND_DIMENSION_CODE,
    BRAND_DIMENSION_NAME,
    BRAND_DIMENSION_TYPE,
    BRAND_STAGE_CODE,
    BRAND_STAGE_NAME,
    BRAND_CONSUMER_COUNT,
    BRAND_CONSUMER_SHARE,
    BRAND_TRANSACTION_AMOUNT,
    BRAND_TRANSACTION_BUYER_COUNT,
    BRAND_CONSUMER_UNIT_PRICE,
    BRAND_CONVERSION_RATE,
    BRAND_RELATIONSHIP_DEEPENING_RATE,
    BRAND_REPURCHASE_PURCHASE_RATIO,
    BRAND_MEMBER_TRANSACTION_AMOUNT,
    BRAND_PREDICTED_CONSUMER_VALUE,
    BUSINESS_DAY,
    LocalDatabase,
    q,
)

ENDPOINT_KEY = "databank.home.daily_snapshot"
PARSER_VERSION = "databank-home-v2"

STAGE_NAMES = {
    "a": "认知人群",
    "i": "兴趣人群",
    "p": "购买人群",
    "l": "忠诚人群",
    "o": "机会人群",
}


class DatabankPayloadError(ValueError):
    pass


def _value(value: Any) -> Any:
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


def _decimal(value: Any) -> str | None:
    value = _value(value)
    if value is None or value == "":
        return None
    try:
        return str(Decimal(str(value)))
    except (TypeError, ValueError, ArithmeticError):
        return str(value)


def _metric(data: Mapping[str, Any], code: str) -> str | None:
    return _decimal(data.get(code))


def parse_payload(
    payload: Mapping[str, Any], *, brand_id: str, business_day: date
) -> dict[str, list[tuple[Any, ...]]]:
    core = payload.get("core") or payload.get("queryCoreVolume") or payload.get("data")
    if not isinstance(core, Mapping):
        raise DatabankPayloadError("missing core snapshot data")
    # Accept either the combined fetch result or the raw queryCoreVolume body.
    if "data" in core and isinstance(core.get("data"), Mapping):
        core = core["data"]
    pay = payload.get("pay") or payload.get("queryPayAnalyse") or {}
    if isinstance(pay, Mapping) and isinstance(pay.get("data"), Mapping):
        pay = pay["data"]
    if not isinstance(pay, Mapping):
        pay = {}
    has_core_value = any(
        Decimal(str(_value(core.get(code)) or 0)) != 0
        for code in (
            "customerVolume",
            "brandPayAmt",
            "purchaseVolume",
            "interestVolume",
            "loyalVolume",
        )
    )
    overview = [
        (
            brand_id,
            business_day.isoformat(),
            "self",
            _metric(core, "customerVolume"),
            _metric(core, "deepenRatio"),
            _metric(core, "aiPlRate"),
            _metric(core, "brandPayAmt"),
            _metric(pay, "brandPayUv"),
            _metric(core, "aiPlRate"),
            _metric(core, "mbrPayAmt"),
            _metric(core, "customerPropertyPred"),
        )
    ]
    stages: list[tuple[Any, ...]] = []
    crowd = payload.get("crowd") or payload.get("queryCrowdAnalyse") or {}
    if isinstance(crowd, Mapping) and isinstance(crowd.get("data"), Mapping):
        crowd = crowd["data"]
    self_rows = crowd.get("self", []) if isinstance(crowd, Mapping) else []
    total = sum(Decimal(str(_value(row.get("customerVolume")) or 0)) for row in self_rows if isinstance(row, Mapping))
    for row in self_rows:
        if not isinstance(row, Mapping):
            continue
        code = str(row.get("aiplStatus") or "")
        count = _value(row.get("customerVolume"))
        share = Decimal(str(count or 0)) / total if total else None
        stages.append((brand_id, business_day.isoformat(), code, STAGE_NAMES.get(code, code), _decimal(count), _decimal(share), _decimal(row.get("brandPayAmt")), _decimal(row.get("brandPayUv")), _decimal(row.get("payRate")), _decimal(row.get("payPbt"))))

    dimensions: list[tuple[Any, ...]] = []
    for kind, rows, name_key in (
        ("category", payload.get("category") or payload.get("chl") or [], "cateName"),
        ("channel", payload.get("channel") or [], "channelName"),
        ("touch", payload.get("touch") or [], "touchLevel2Name"),
    ):
        if isinstance(rows, Mapping):
            rows = rows.get("data", [])
        for index, row in enumerate(rows if isinstance(rows, list) else []):
            if not isinstance(row, Mapping):
                continue
            name = str(row.get(name_key) or row.get("touchLevel1Name") or "")
            dimensions.append((brand_id, business_day.isoformat(), kind, f"{kind}:{index}", name, None, None, _decimal(row.get("brandPayAmt")), _decimal(row.get("brandPayUv")), None, _decimal(row.get("brandCustomerValue"))))
    metrics: list[tuple[Any, ...]] = []

    def add_metric(kind: str, code: str, name: str, value: Any, *, period_start: str | None = None, period_end: str | None = None) -> None:
        if value is None:
            return
        metrics.append((brand_id, business_day.isoformat(), kind, code, name, _decimal(value), period_start, period_end))

    snapshot_ds = business_day.strftime("%Y%m%d")

    # The volume endpoint supplies the daily AIPL asset shares that are not
    # represented by the wide overview row.  Keep the raw metric name and
    # source grouping so future UI/reporting changes do not lose information.
    volume = payload.get("volume") or payload.get("queryVolume") or {}
    if isinstance(volume, Mapping) and isinstance(volume.get("data"), Mapping):
        volume = volume["data"]
    if isinstance(volume, Mapping):
        for code, name in (
            ("awarenessVolumePer", "认知人群占比"),
            ("interestVolumePer", "兴趣人群占比"),
            ("purchaseVolumePer", "购买人群占比"),
            ("loyalVolumePer", "忠诚人群占比"),
        ):
            add_metric("volume", code, name, volume.get(code))

    # Preserve the comparison dimensions returned by crowd analysis.  This
    # includes customer volume, view/cart/pay users, conversion and unit
    # price for both the brand itself and the comparison population.
    if isinstance(crowd, Mapping):
        for scope in ("self", "compare"):
            rows = crowd.get(scope, [])
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, Mapping):
                    continue
                stage = str(row.get("aiplStatus") or "")
                for code, name in (
                    ("customerVolume", "消费者数"),
                    ("viewUv", "浏览人数"),
                    ("cartCltUv", "加购收藏人数"),
                    ("brandPayUv", "成交人数"),
                    ("brandPayAmt", "成交金额"),
                    ("viewRate", "浏览率"),
                    ("cartCltRate", "加购收藏率"),
                    ("payRate", "成交转化率"),
                    ("payPbt", "成交客单价"),
                    ("brandPayAmtPer", "成交金额占比"),
                ):
                    add_metric(f"crowd_{scope}", stage, name, row.get(code))
    # New homepage business panel.  Scalar values are stored as-is; trend
    # rows retain their source date in the period columns while remaining
    # attached to the requested snapshot day.
    panel = payload.get("homepage_panel") or {}
    if isinstance(panel, Mapping):
        for code, name in (
            ("aiplCnt", "资产人数"),
            ("activeCnt", "活跃人数"),
            ("dealCnt", "成交人数"),
            ("activeChainRadio", "活跃链路占比"),
            ("aiplChainRadio", "资产链路占比"),
            ("dealChainRadio", "成交链路占比"),
        ):
            add_metric("homepage_panel", code, name, panel.get(code))
        for row in panel.get("list", []) if isinstance(panel.get("list"), list) else []:
            if not isinstance(row, Mapping):
                continue
            if str(row.get("ds") or "") != snapshot_ds:
                continue
            period = business_day.isoformat()
            for code, name in (("aiplCnt", "资产人数"), ("activeCnt", "活跃人数"), ("dealCnt", "成交人数")):
                add_metric("homepage_panel_trend", code, name, row.get(code), period_start=period, period_end=period)

    growth = payload.get("homepage_growth_strategy") or {}
    if isinstance(growth, Mapping):
        for code, name in (
            ("touchUV", "触达人数"),
            ("touchPV", "人均触达次数"),
            ("activeTime", "人均停留时长"),
            ("ctr", "人均触达点击率"),
            ("cvr", "人均触达转化率"),
            ("touchUVMedian", "触达人数行业中位值"),
            ("touchPVMedian", "人均触达次数行业中位值"),
            ("activeTimeMedian", "人均停留时长行业中位值"),
            ("ctrMedian", "人均触达点击率行业中位值"),
            ("cvrMedian", "人均触达转化率行业中位值"),
        ):
            add_metric("homepage_growth_strategy", code, name, growth.get(code))

    for key, panel_type, label in (
        ("homepage_panel_detail_active", "active", "经营面板-活跃"),
        ("homepage_panel_detail_aipl", "aipl", "经营面板-AIPL"),
        ("homepage_panel_detail_deal", "deal", "经营面板-成交"),
    ):
        detail = payload.get(key) or {}
        if not isinstance(detail, Mapping):
            continue
        for code, value in detail.items():
            if code == "list":
                continue
            add_metric("homepage_detail", f"{panel_type}.{code}", f"{label}.{code}", value)
        for row in detail.get("list", []) if isinstance(detail.get("list"), list) else []:
            if not isinstance(row, Mapping):
                continue
            if str(row.get("ds") or "") != snapshot_ds:
                continue
            period = business_day.isoformat()
            for code, value in row.items():
                if code == "ds":
                    continue
                add_metric("homepage_detail_trend", f"{panel_type}.{code}", f"{label}.{code}", value, period_start=period, period_end=period)

    for key, panel_type in (
        ("homepage_growth_map_touch", "touch"),
        ("homepage_growth_map_avg_touch", "avgTouch"),
        ("homepage_growth_map_active_time", "activeTime"),
        ("homepage_growth_map_ctr", "ctr"),
        ("homepage_growth_map_cvr", "cvr"),
    ):
        rows = payload.get(key) or []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, Mapping):
                continue
            if str(row.get("ds") or "") != snapshot_ds:
                continue
            period = business_day.isoformat()
            add_metric("homepage_growth_map", f"{panel_type}.brandValue", f"{panel_type}.品牌值", row.get("brandValue"), period_start=period, period_end=period)
            add_metric("homepage_growth_map", f"{panel_type}.medianValue", f"{panel_type}.行业中位值", row.get("medianValue"), period_start=period, period_end=period)

    if not has_core_value and not stages and not dimensions and not metrics:
        return {"overview": [], "stages": [], "dimensions": [], "metrics": []}
    return {"overview": overview, "stages": stages, "dimensions": dimensions, "metrics": metrics}


def ingest_snapshot(
    database_path, *, brand_id: str, business_day: date, payload: Mapping[str, Any]
) -> dict[str, int]:
    parsed = parse_payload(payload, brand_id=brand_id, business_day=business_day)
    db = LocalDatabase(database_path)
    with db.connect(initialize=True) as conn:
        conn.execute(f"delete from {q(BRAND_ASSET_OVERVIEW_TABLE)} where {q(BRAND_ID)}=? and {q(BUSINESS_DAY)}=?", (brand_id, business_day.isoformat()))
        conn.execute(f"delete from {q(BRAND_ASSET_STAGE_TABLE)} where {q(BRAND_ID)}=? and {q(BUSINESS_DAY)}=?", (brand_id, business_day.isoformat()))
        conn.execute(f"delete from {q(BRAND_ASSET_DIMENSION_TABLE)} where {q(BRAND_ID)}=? and {q(BUSINESS_DAY)}=?", (brand_id, business_day.isoformat()))
        if LocalDatabase._table_exists(conn, BRAND_ASSET_METRICS_TABLE):
            conn.execute(f"delete from {q(BRAND_ASSET_METRICS_TABLE)} where {q(BRAND_ID)}=? and {q(BUSINESS_DAY)}=?", (brand_id, business_day.isoformat()))
        for table, rows in (
            (BRAND_ASSET_OVERVIEW_TABLE, parsed["overview"]),
            (BRAND_ASSET_STAGE_TABLE, parsed["stages"]),
            (BRAND_ASSET_DIMENSION_TABLE, parsed["dimensions"]),
            (BRAND_ASSET_METRICS_TABLE, parsed["metrics"]),
        ):
            if rows and LocalDatabase._table_exists(conn, table):
                conn.executemany(
                    f"insert into {q(table)} values ({','.join('?' for _ in rows[0])})",
                    rows,
                )
    return {key: len(value) for key, value in parsed.items()}
