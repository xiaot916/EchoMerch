from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import RowMapping

from app.core.config import settings
from app.modules.analytics.schemas import (
    DailyMetric,
    DataFreshness,
    ProductMetric,
    PromotionDailyMetric,
    PromotionMetric,
    TrafficMetric,
)


class LegacyDatabaseNotConfigured(RuntimeError):
    pass


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _to_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class LegacyAdorAnalyticsRepository:
    """Read-only adapter for the current Chinese-column reporting schema."""

    def __init__(self, engine: Engine | None = None) -> None:
        if engine is not None:
            self._engine = engine
            return
        if not settings.legacy_database_url:
            raise LegacyDatabaseNotConfigured(
                "LEGACY_DATABASE_URL is required to query the historical reporting database."
            )
        self._engine = create_engine(
            settings.legacy_database_url,
            pool_pre_ping=True,
            future=True,
        )

    def _rows(self, statement: str, **params: object) -> list[RowMapping]:
        with self._engine.connect() as connection:
            # A belt-and-suspenders guard: this adapter is intended to remain read-only.
            connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
            return list(connection.execute(text(statement), params).mappings())

    def get_date_bounds(self) -> tuple[date, date]:
        rows = self._rows(
            """
            SELECT MIN(`日期`) AS min_date, MAX(`日期`) AS max_date
            FROM `dailyshopdata`
            """
        )
        if not rows or not rows[0]["max_date"]:
            raise RuntimeError("The legacy store daily report does not contain any data.")
        return _to_date(rows[0]["min_date"]), _to_date(rows[0]["max_date"])

    def get_daily_metrics(self, start_date: date, end_date: date) -> list[DailyMetric]:
        rows = self._rows(
            """
            SELECT
                `日期` AS stat_date,
                `支付金额` AS paid_amount,
                `访客数` AS visitors,
                `支付转化率` AS conversion_rate,
                `全站推广花费` AS promotion_cost,
                `支付买家数` AS buyers
            FROM `dailyshopdata`
            WHERE `日期` BETWEEN :start_date AND :end_date
            ORDER BY `日期`
            """,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            DailyMetric(
                stat_date=_to_date(row["stat_date"]),
                paid_amount=_to_decimal(row["paid_amount"]),
                visitors=int(row["visitors"] or 0),
                conversion_rate=_to_decimal(row["conversion_rate"]),
                promotion_cost=_to_decimal(row["promotion_cost"]),
                buyers=int(row["buyers"] or 0),
            )
            for row in rows
        ]

    def get_promotion_daily_metrics(
        self,
        start_date: date,
        end_date: date,
    ) -> list[PromotionDailyMetric]:
        return []

    def get_product_date_bounds(self) -> tuple[date, date]:
        rows = self._rows(
            """
            SELECT
                MIN(STR_TO_DATE(`日期`, '%Y-%m-%d')) AS min_date,
                MAX(STR_TO_DATE(`日期`, '%Y-%m-%d')) AS max_date
            FROM `product_sales_daily`
            """
        )
        if not rows or not rows[0]["max_date"]:
            raise RuntimeError("The legacy product sales report does not contain any data.")
        return _to_date(rows[0]["min_date"]), _to_date(rows[0]["max_date"])

    def get_top_products(self, start_date: date, end_date: date) -> list[ProductMetric]:
        rows = self._rows(
            """
            SELECT
                `商品ID` AS product_id,
                MAX(`商品名称`) AS product_name,
                SUM(COALESCE(`支付金额`, 0)) AS paid_amount,
                SUM(COALESCE(`支付买家数`, 0)) AS buyers,
                SUM(COALESCE(`商品访客数`, 0)) AS visitors
            FROM `product_sales_daily`
            WHERE STR_TO_DATE(`日期`, '%Y-%m-%d') BETWEEN :start_date AND :end_date
            GROUP BY `商品ID`
            ORDER BY paid_amount DESC
            LIMIT 8
            """,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            ProductMetric(
                product_id=str(row["product_id"] or ""),
                product_name=str(row["product_name"] or "未命名商品"),
                paid_amount=_to_decimal(row["paid_amount"]),
                buyers=int(row["buyers"] or 0),
                visitors=int(row["visitors"] or 0),
            )
            for row in rows
        ]

    def get_traffic_sources(self, start_date: date, end_date: date) -> list[TrafficMetric]:
        rows = self._rows(
            """
            SELECT
                `一级来源` AS source_name,
                SUM(COALESCE(`访客数`, 0)) AS visitors,
                SUM(COALESCE(`支付金额`, 0)) AS paid_amount,
                SUM(COALESCE(`支付买家数`, 0)) AS buyers
            FROM `traffic_source`
            WHERE STR_TO_DATE(`日期`, '%Y-%m-%d') BETWEEN :start_date AND :end_date
            GROUP BY `一级来源`
            ORDER BY paid_amount DESC
            LIMIT 6
            """,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            TrafficMetric(
                source_name=str(row["source_name"] or "未分类"),
                visitors=int(row["visitors"] or 0),
                paid_amount=_to_decimal(row["paid_amount"]),
                buyers=int(row["buyers"] or 0),
            )
            for row in rows
        ]

    def get_top_promotion_plans(self, start_date: date, end_date: date) -> list[PromotionMetric]:
        rows = self._rows(
            """
            SELECT
                COALESCE(NULLIF(`计划名字`, ''), '未命名计划') AS plan_name,
                SUM(COALESCE(`花费`, 0)) AS spend,
                SUM(COALESCE(`总成交金额`, 0)) AS paid_amount,
                SUM(COALESCE(`成交人数`, 0)) AS buyers
            FROM `rtb_plan_data`
            WHERE `日期` BETWEEN :start_date AND :end_date
            GROUP BY `计划ID`, `计划名字`
            ORDER BY spend DESC
            LIMIT 6
            """,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            PromotionMetric(
                plan_name=str(row["plan_name"]),
                spend=_to_decimal(row["spend"]),
                paid_amount=_to_decimal(row["paid_amount"]),
                buyers=int(row["buyers"] or 0),
            )
            for row in rows
        ]

    def get_freshness(self) -> list[DataFreshness]:
        rows = self._rows(
            """
            SELECT '店铺总览' AS dataset, MAX(`日期`) AS latest_date FROM `dailyshopdata`
            UNION ALL
            SELECT '商品表现' AS dataset, MAX(STR_TO_DATE(`日期`, '%Y-%m-%d')) AS latest_date FROM `product_sales_daily`
            UNION ALL
            SELECT '流量来源' AS dataset, MAX(STR_TO_DATE(`日期`, '%Y-%m-%d')) AS latest_date FROM `traffic_source`
            UNION ALL
            SELECT '推广计划' AS dataset, MAX(`日期`) AS latest_date FROM `rtb_plan_data`
            """
        )
        return [
            DataFreshness(dataset=str(row["dataset"]), latest_date=_to_date(row["latest_date"]))
            for row in rows
            if row["latest_date"]
        ]

    @staticmethod
    def default_range(maximum: date) -> tuple[date, date]:
        return maximum - timedelta(days=6), maximum
