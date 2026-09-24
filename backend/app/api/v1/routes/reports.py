"""大屏聚合 API — 基于本地 SQLite 仓库存的多表聚合查询。

提供四个端点：
- /reports/big-screen/summary        全渠道 KPI + 增长因子 + 体验分 + 层级信息
- /reports/big-screen/trends         按日趋势序列（成交 / 访客 / 推广花费 / 推广成交）
- /reports/big-screen/traffic        流量来源结构（Top 10 一级来源）
- /reports/big-screen/promotion-roi  推广计划 ROI 排行（Top 10）
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.dependencies import require_permission, resolve_store_scope
from app.core.config import settings
from app.core.local_database import LocalDatabase, q
from app.modules.access.service import Principal

router = APIRouter()

# ── 常量 ─────────────────────────────────────────────────────

_STORE_ID_SQL = q("店铺ID")
_BIZ_DAY_SQL = q("业务日期")

# store_daily_overviews columns
_OV_PAID = q("支付金额")
_OV_VISITORS = q("访客数")
_OV_PAID_BUYERS = q("支付买家数")
_OV_REFUND = q("退款金额（完结时间）")
# Promotion KPIs (spend and attributed GMV) come from the Alimama campaign
# warehouse (`store_daily_promotion_campaigns`) so that the big-screen KPI,
# the campaign Top-10 table and the dashboard page all share the same
# definition: 归因总成交 / 计划花费. `store_daily_overviews` has no
# promotion-attributed GMV column — using its 总支付金额 there previously
# produced a whole-store GMV/spend ratio that was mislabeled as ROI.

# store_daily_traffic_sources
_TRAFFIC_L1 = q("一级来源")
_TRAFFIC_VISITORS = q("访客数")
_TRAFFIC_PAID = q("支付金额")

# store_daily_promotion_campaigns
_PROMO_CAMPAIGN_ID = q("推广计划ID")
_PROMO_CAMPAIGN_NAME = q("推广计划名称")
_PROMO_SPEND = q("花费")
_PROMO_PAID = q("总成交金额")

# store_daily_sycm_home_board
_HB_TRANSACTION = q("增长因子_交易分")
_HB_TRAFFIC = q("增长因子_流量分")
_HB_ITEM = q("增长因子_商品分")
_HB_MARKETING = q("增长因子_营销分")
_HB_SERVICE = q("增长因子_服务分")
_HB_EXP_TOTAL = q("体验总分")
_HB_EXP_ITEM = q("商品体验分")
_HB_EXP_LOGISTICS = q("物流体验分")
_HB_EXP_SERVICE = q("服务体验分")
_HB_EXP_REFUND = q("退款体验分")
_HB_EXP_DISPUTE = q("纠纷体验分")
_HB_LEVEL = q("层级等级")
_HB_LEVEL_SCORE = q("层级分数")
_HB_LEVEL_PCT = q("层级排名百分位")


def _database() -> LocalDatabase:
    db = LocalDatabase(Path(settings.local_database_path))
    db.initialize_schema()
    return db


def _safe_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(value)
    except (TypeError, ValueError):
        return None


# ── Pydantic Schemas ─────────────────────────────────────────

class KpiBlock(BaseModel):
    paid_amount: str
    visitors: int
    buyers: int
    conversion_rate: str
    promotion_cost: str
    promotion_paid_amount: str
    promotion_roi: str
    refund_amount: str
    net_paid_amount: str


class GrowthFactorBlock(BaseModel):
    transaction_score: str | None
    traffic_score: str | None
    item_score: str | None
    marketing_score: str | None
    service_score: str | None


class ExperienceScoreBlock(BaseModel):
    total_score: str | None
    item_score: str | None
    logistics_score: str | None
    service_score: str | None
    refund_score: str | None
    dispute_score: str | None


class LevelInfoBlock(BaseModel):
    level: str | None
    score: str | None
    rank_percentile: str | None


class BigScreenSummaryResponse(BaseModel):
    range_start: str
    range_end: str
    days: int
    kpi: KpiBlock
    growth_factor: GrowthFactorBlock
    experience_score: ExperienceScoreBlock
    level_info: LevelInfoBlock


class TrendPoint(BaseModel):
    date: str
    paid_amount: str
    visitors: int
    promotion_cost: str
    promotion_paid_amount: str


class BigScreenTrendsResponse(BaseModel):
    range_start: str
    range_end: str
    points: list[TrendPoint]


class TrafficSourceItem(BaseModel):
    name: str
    visitors: int
    paid_amount: str
    share_percent: str


class BigScreenTrafficResponse(BaseModel):
    range_start: str
    range_end: str
    total_paid_amount: str
    sources: list[TrafficSourceItem]


class PromoRoiItem(BaseModel):
    campaign_id: str
    campaign_name: str
    spend: str
    paid_amount: str
    roi: str


class BigScreenPromoRoiResponse(BaseModel):
    range_start: str
    range_end: str
    campaigns: list[PromoRoiItem]


# ── 内部工具函数 ─────────────────────────────────────────────

def _default_store_id(db: LocalDatabase) -> int | None:
    """Fallback store when the caller has no explicit store scope.

    Super administrators have ``store_ids=None``, so ``resolve_store_scope``
    returns ``None`` for them. Querying with ``店铺ID = NULL`` matches nothing
    and silently yields an all-zero dashboard, so fall back to the store that
    actually has fact rows.
    """
    with db.connect() as conn:
        row = conn.execute(
            f'select min({_STORE_ID_SQL}) as sid '
            f'from store_daily_overviews where {_STORE_ID_SQL} is not null'
        ).fetchone()
    return int(row["sid"]) if row and row["sid"] is not None else None


def _date_range(
    start_date: date | None,
    end_date: date | None,
    db: LocalDatabase,
    store_id: int,
) -> tuple[date, date]:
    with db.connect() as conn:
        row = conn.execute(
            f'select min({q("业务日期")}) as d0, max({q("业务日期")}) as d1 '
            f'from store_daily_overviews where {_STORE_ID_SQL} = ?',
            (store_id,),
        ).fetchone()
    minimum = date.fromisoformat(str(row["d0"])) if row and row["d0"] else date.today() - timedelta(days=30)
    maximum = date.fromisoformat(str(row["d1"])) if row and row["d1"] else date.today() - timedelta(days=1)
    resolved_start = start_date or (maximum - timedelta(days=29))
    resolved_end = end_date or maximum
    if resolved_start < minimum:
        resolved_start = minimum
    if resolved_end > maximum:
        resolved_end = maximum
    if resolved_start > resolved_end:
        raise ValueError("日期范围无效")
    return resolved_start, resolved_end


def _promotion_totals(db: LocalDatabase, store_id: int, start: date, end: date) -> dict[str, Decimal]:
    """Range totals for promotion spend and attributed paid GMV from the
    Alimama campaign warehouse — the same source as the campaign Top-10
    table, so KPI and table can never disagree."""
    with db.connect() as conn:
        row = conn.execute(
            f"""
            select
                coalesce(sum({_PROMO_SPEND}), 0) as spend,
                coalesce(sum({_PROMO_PAID}), 0)  as paid_amount
            from store_daily_promotion_campaigns
            where {_STORE_ID_SQL} = ? and {q("业务日期")} between ? and ?
            """,
            (store_id, start.isoformat(), end.isoformat()),
        ).fetchone()
    return {
        "spend": _safe_decimal(row["spend"]),
        "paid_amount": _safe_decimal(row["paid_amount"]),
    }


def _aggregate_kpi(db: LocalDatabase, store_id: int, start: date, end: date) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute(
            f"""
            select
                coalesce(sum({_OV_PAID}), 0)                          as paid_amount,
                coalesce(sum({_OV_VISITORS}), 0)                      as visitors,
                coalesce(sum({_OV_PAID_BUYERS}), 0)                   as buyers,
                coalesce(sum({_OV_REFUND}), 0)                        as refund_amount
            from store_daily_overviews
            where {_STORE_ID_SQL} = ? and {q("业务日期")} between ? and ?
            """,
            (store_id, start.isoformat(), end.isoformat()),
        ).fetchone()
    promotion = _promotion_totals(db, store_id, start, end)
    paid_amount = _safe_decimal(row["paid_amount"])
    visitors = int(_safe_decimal(row["visitors"]))
    buyers = int(_safe_decimal(row["buyers"]))
    refund_amount = _safe_decimal(row["refund_amount"])
    promotion_cost = promotion["spend"]
    promotion_paid_amount = promotion["paid_amount"]
    conversion_rate = (Decimal(buyers) / Decimal(visitors) * 100) if visitors else Decimal("0")
    roi = (promotion_paid_amount / promotion_cost) if promotion_cost else Decimal("0")
    return {
        "paid_amount": str(paid_amount.quantize(Decimal("0.01"))),
        "visitors": visitors,
        "buyers": buyers,
        "conversion_rate": str(conversion_rate.quantize(Decimal("0.01"))),
        "promotion_cost": str(promotion_cost.quantize(Decimal("0.01"))),
        "promotion_paid_amount": str(promotion_paid_amount.quantize(Decimal("0.01"))),
        "promotion_roi": str(roi.quantize(Decimal("0.01"))),
        "refund_amount": str(refund_amount.quantize(Decimal("0.01"))),
        "net_paid_amount": str((paid_amount - refund_amount).quantize(Decimal("0.01"))),
    }


def _latest_home_board(db: LocalDatabase, store_id: int) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute(
            f"""
            select
                {_HB_TRANSACTION}  as transaction_score,
                {_HB_TRAFFIC}      as traffic_score,
                {_HB_ITEM}         as item_score,
                {_HB_MARKETING}   as marketing_score,
                {_HB_SERVICE}      as service_score,
                {_HB_EXP_TOTAL}    as exp_total,
                {_HB_EXP_ITEM}     as exp_item,
                {_HB_EXP_LOGISTICS} as exp_logistics,
                {_HB_EXP_SERVICE}  as exp_service,
                {_HB_EXP_REFUND}   as exp_refund,
                {_HB_EXP_DISPUTE}  as exp_dispute,
                {_HB_LEVEL}        as level,
                {_HB_LEVEL_SCORE}  as level_score,
                {_HB_LEVEL_PCT}    as level_rank_pct,
                {q("业务日期")}     as biz_day
            from store_daily_sycm_home_board
            where {_STORE_ID_SQL} = ?
            order by {q("业务日期")} desc
            limit 1
            """,
            (store_id,),
        ).fetchone()
    if row is None:
        return {}
    return dict(row)


# ── 端点 ─────────────────────────────────────────────────────

@router.get("/big-screen/summary", response_model=BigScreenSummaryResponse)
def big_screen_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> BigScreenSummaryResponse:
    db = _database()
    resolved_store = resolve_store_scope(principal, store_id)
    if resolved_store is None:
        resolved_store = _default_store_id(db)
    if resolved_store is None:
        raise HTTPException(status_code=404, detail="本地仓库暂无可用店铺数据。")
    try:
        start, end = _date_range(start_date, end_date, db, resolved_store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    kpi = _aggregate_kpi(db, resolved_store, start, end)
    hb = _latest_home_board(db, resolved_store)
    days = (end - start).days + 1
    return BigScreenSummaryResponse(
        range_start=start.isoformat(),
        range_end=end.isoformat(),
        days=days,
        kpi=KpiBlock(**kpi),
        growth_factor=GrowthFactorBlock(
            transaction_score=_opt_str(hb.get("transaction_score")),
            traffic_score=_opt_str(hb.get("traffic_score")),
            item_score=_opt_str(hb.get("item_score")),
            marketing_score=_opt_str(hb.get("marketing_score")),
            service_score=_opt_str(hb.get("service_score")),
        ),
        experience_score=ExperienceScoreBlock(
            total_score=_opt_str(hb.get("exp_total")),
            item_score=_opt_str(hb.get("exp_item")),
            logistics_score=_opt_str(hb.get("exp_logistics")),
            service_score=_opt_str(hb.get("exp_service")),
            refund_score=_opt_str(hb.get("exp_refund")),
            dispute_score=_opt_str(hb.get("exp_dispute")),
        ),
        level_info=LevelInfoBlock(
            level=_opt_str(hb.get("level")),
            score=_opt_str(hb.get("level_score")),
            rank_percentile=_opt_str(hb.get("level_rank_pct")),
        ),
    )


@router.get("/big-screen/trends", response_model=BigScreenTrendsResponse)
def big_screen_trends(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> BigScreenTrendsResponse:
    db = _database()
    resolved_store = resolve_store_scope(principal, store_id)
    if resolved_store is None:
        resolved_store = _default_store_id(db)
    if resolved_store is None:
        raise HTTPException(status_code=404, detail="本地仓库暂无可用店铺数据。")
    try:
        start, end = _date_range(start_date, end_date, db, resolved_store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            select
                {q("业务日期")} as d,
                coalesce(sum({_OV_PAID}), 0)           as paid_amount,
                coalesce(sum({_OV_VISITORS}), 0)       as visitors
            from store_daily_overviews
            where {_STORE_ID_SQL} = ? and {q("业务日期")} between ? and ?
            group by {q("业务日期")}
            order by {q("业务日期")}
            """,
            (resolved_store, start.isoformat(), end.isoformat()),
        ).fetchall()
        promo_rows = conn.execute(
            f"""
            select
                {q("业务日期")} as d,
                coalesce(sum({_PROMO_SPEND}), 0) as promotion_cost,
                coalesce(sum({_PROMO_PAID}), 0)  as promotion_paid_amount
            from store_daily_promotion_campaigns
            where {_STORE_ID_SQL} = ? and {q("业务日期")} between ? and ?
            group by {q("业务日期")}
            order by {q("业务日期")}
            """,
            (resolved_store, start.isoformat(), end.isoformat()),
        ).fetchall()
    row_map: dict[str, Any] = {str(r["d"]): r for r in rows}
    promo_map: dict[str, Any] = {str(r["d"]): r for r in promo_rows}
    points: list[TrendPoint] = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        r = row_map.get(key)
        p = promo_map.get(key)
        points.append(TrendPoint(
            date=key,
            paid_amount=str(_safe_decimal(r["paid_amount"] if r else 0).quantize(Decimal("0.01"))),
            visitors=int(_safe_decimal(r["visitors"] if r else 0)),
            promotion_cost=str(_safe_decimal(p["promotion_cost"] if p else 0).quantize(Decimal("0.01"))),
            promotion_paid_amount=str(_safe_decimal(p["promotion_paid_amount"] if p else 0).quantize(Decimal("0.01"))),
        ))
    return BigScreenTrendsResponse(
        range_start=start.isoformat(),
        range_end=end.isoformat(),
        points=points,
    )


@router.get("/big-screen/traffic", response_model=BigScreenTrafficResponse)
def big_screen_traffic(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> BigScreenTrafficResponse:
    db = _database()
    resolved_store = resolve_store_scope(principal, store_id)
    if resolved_store is None:
        resolved_store = _default_store_id(db)
    if resolved_store is None:
        raise HTTPException(status_code=404, detail="本地仓库暂无可用店铺数据。")
    try:
        start, end = _date_range(start_date, end_date, db, resolved_store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with db.connect() as conn:
        total_row = conn.execute(
            f"select coalesce(sum({_TRAFFIC_PAID}), 0) as total "
            f"from store_daily_traffic_sources "
            f"where {_STORE_ID_SQL} = ? and {q('业务日期')} between ? and ?",
            (resolved_store, start.isoformat(), end.isoformat()),
        ).fetchone()
        rows = conn.execute(
            f"""
            select
                {_TRAFFIC_L1} as src,
                coalesce(sum({_TRAFFIC_VISITORS}), 0) as visitors,
                coalesce(sum({_TRAFFIC_PAID}), 0)      as paid_amount
            from store_daily_traffic_sources
            where {_STORE_ID_SQL} = ?
              and {q("业务日期")} between ? and ?
              and {q("来源层级")} = 1
              and {_TRAFFIC_L1} is not null
              and {_TRAFFIC_L1} != ''
            group by {_TRAFFIC_L1}
            order by paid_amount desc
            limit 10
            """,
            (resolved_store, start.isoformat(), end.isoformat()),
        ).fetchall()
    total_paid = _safe_decimal(total_row["total"] if total_row else 0)
    sources: list[TrafficSourceItem] = []
    for r in rows:
        paid = _safe_decimal(r["paid_amount"])
        share = (paid / total_paid * 100) if total_paid else Decimal("0")
        sources.append(TrafficSourceItem(
            name=str(r["src"]),
            visitors=int(_safe_decimal(r["visitors"])),
            paid_amount=str(paid.quantize(Decimal("0.01"))),
            share_percent=str(share.quantize(Decimal("0.01"))),
        ))
    return BigScreenTrafficResponse(
        range_start=start.isoformat(),
        range_end=end.isoformat(),
        total_paid_amount=str(total_paid.quantize(Decimal("0.01"))),
        sources=sources,
    )


@router.get("/big-screen/promotion-roi", response_model=BigScreenPromoRoiResponse)
def big_screen_promotion_roi(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> BigScreenPromoRoiResponse:
    db = _database()
    resolved_store = resolve_store_scope(principal, store_id)
    if resolved_store is None:
        resolved_store = _default_store_id(db)
    if resolved_store is None:
        raise HTTPException(status_code=404, detail="本地仓库暂无可用店铺数据。")
    try:
        start, end = _date_range(start_date, end_date, db, resolved_store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            select
                coalesce({_PROMO_CAMPAIGN_ID}, '') as campaign_id,
                coalesce({_PROMO_CAMPAIGN_NAME}, '') as campaign_name,
                coalesce(sum({_PROMO_SPEND}), 0)  as spend,
                coalesce(sum({_PROMO_PAID}), 0)   as paid_amount
            from store_daily_promotion_campaigns
            where {_STORE_ID_SQL} = ? and {q("业务日期")} between ? and ?
            group by {_PROMO_CAMPAIGN_ID}, {_PROMO_CAMPAIGN_NAME}
            order by paid_amount desc
            limit 10
            """,
            (resolved_store, start.isoformat(), end.isoformat()),
        ).fetchall()
    campaigns: list[PromoRoiItem] = []
    for r in rows:
        spend = _safe_decimal(r["spend"])
        paid = _safe_decimal(r["paid_amount"])
        roi = (paid / spend) if spend else Decimal("0")
        campaigns.append(PromoRoiItem(
            campaign_id=str(r["campaign_id"] or "—"),
            campaign_name=str(r["campaign_name"] or "未命名计划"),
            spend=str(spend.quantize(Decimal("0.01"))),
            paid_amount=str(paid.quantize(Decimal("0.01"))),
            roi=str(roi.quantize(Decimal("0.01"))),
        ))
    return BigScreenPromoRoiResponse(
        range_start=start.isoformat(),
        range_end=end.isoformat(),
        campaigns=campaigns,
    )
