from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from app.integrations.contracts import AnalyticsSource
from app.integrations.legacy_ador.repository import LegacyAdorAnalyticsRepository
from app.integrations.local_warehouse.repository import LocalWarehouseAnalyticsRepository
from app.core.config import settings
from app.modules.analytics.schemas import (
    BusinessInsight,
    ComparisonMetric,
    DashboardPeriod,
    DataCoverage,
    DashboardResponse,
    SummaryComparison,
    SummaryMetric,
)


class AnalyticsService:
    def __init__(self, source: AnalyticsSource | None = None) -> None:
        self._source = source

    @property
    def source(self) -> AnalyticsSource:
        if self._source is None:
            if settings.legacy_database_url:
                self._source = LegacyAdorAnalyticsRepository()
            else:
                self._source = LocalWarehouseAnalyticsRepository(
                    Path(settings.local_database_path),
                    store_id=settings.default_store_id,
                )
        return self._source

    def _source_for_store(self, store_id: int | None) -> AnalyticsSource:
        if self._source is not None or settings.legacy_database_url or store_id is None:
            return self.source
        return LocalWarehouseAnalyticsRepository(
            Path(settings.local_database_path),
            store_id=store_id,
        )

    def get_dashboard(
        self,
        start_date: date | None,
        end_date: date | None,
        store_id: int | None = None,
    ) -> DashboardResponse:
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")

        source = self._source_for_store(store_id)
        minimum, maximum = source.get_date_bounds()
        default_start, default_end = source.default_range(maximum)
        range_start = start_date or default_start
        range_end = end_date or default_end
        if range_end > maximum:
            raise ValueError(f"end_date cannot be later than the latest available date ({maximum.isoformat()})")
        if range_start > range_end:
            raise ValueError("start_date must be earlier than or equal to end_date")

        daily_metrics = source.get_daily_metrics(range_start, range_end)
        get_promotion_daily_metrics = getattr(source, "get_promotion_daily_metrics", None)
        promotion_daily_metrics = (
            get_promotion_daily_metrics(range_start, range_end)
            if get_promotion_daily_metrics is not None
            else None
        )
        products = source.get_top_products(range_start, range_end)
        product_range_start = range_start
        product_range_end = range_end

        summary = self._summarize(daily_metrics, promotion_daily_metrics)
        period_days = (range_end - range_start).days + 1
        previous_end = range_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        previous_daily_metrics = source.get_daily_metrics(previous_start, previous_end)
        previous_promotion_daily_metrics = (
            get_promotion_daily_metrics(previous_start, previous_end)
            if get_promotion_daily_metrics is not None
            else None
        )
        previous_summary = self._summarize(previous_daily_metrics, previous_promotion_daily_metrics)
        comparison = SummaryComparison(
            paid_amount=self._compare(summary.paid_amount, previous_summary.paid_amount),
            visitors=self._compare(Decimal(summary.visitors), Decimal(previous_summary.visitors)),
            buyers=self._compare(Decimal(summary.buyers), Decimal(previous_summary.buyers)),
            conversion_rate=self._compare(summary.conversion_rate, previous_summary.conversion_rate),
            promotion_cost=self._compare(summary.promotion_cost, previous_summary.promotion_cost),
            customer_unit_price=self._compare(summary.customer_unit_price, previous_summary.customer_unit_price),
        )
        get_data_coverage = getattr(source, "get_data_coverage", None)
        coverage = get_data_coverage(range_start, range_end) if get_data_coverage else []
        primary_coverage = next((item for item in coverage if item.dataset in {"店铺日概览", "店铺总览"}), None)
        covered_days = len({metric.stat_date for metric in daily_metrics})
        missing_dates = [
            range_start + timedelta(days=offset)
            for offset in range(period_days)
            if range_start + timedelta(days=offset) not in {metric.stat_date for metric in daily_metrics}
        ]
        if primary_coverage is None:
            primary_coverage = DataCoverage(
                dataset="店铺日概览",
                first_date=minimum,
                latest_date=maximum,
                expected_days=period_days,
                covered_days=covered_days,
                missing_dates=missing_dates,
                status="empty" if not daily_metrics else "complete" if not missing_dates else "partial",
            )
            coverage = [primary_coverage, *coverage]

        # 当前店铺日概览不完整时，当前区间与完整上一周期不可直接比较。
        # 保留 current / previous / delta 供审计，但不输出环比百分比，避免把缺失日造成的差异当成经营变化。
        if primary_coverage.status != "complete":
            comparison = self._without_change_percent(comparison)

        analysis = None
        get_analysis_snapshot = getattr(source, "get_analysis_snapshot", None)
        if get_analysis_snapshot is not None:
            analysis = get_analysis_snapshot(range_start, range_end)
        get_promotion_scenes = getattr(source, "get_promotion_scenes", None)
        promotion_scenes = (
            get_promotion_scenes(range_start, range_end)
            if get_promotion_scenes is not None
            else []
        )

        return DashboardResponse(
            range_start=range_start,
            range_end=range_end,
            product_range_start=product_range_start,
            product_range_end=product_range_end,
            summary=summary,
            daily_metrics=daily_metrics,
            promotion_daily_metrics=promotion_daily_metrics or [],
            top_products=products,
            traffic_sources=source.get_traffic_sources(range_start, range_end),
            promotion_plans=source.get_top_promotion_plans(range_start, range_end),
            promotion_scenes=promotion_scenes,
            freshness=source.get_freshness(),
            period=DashboardPeriod(
                requested_start=range_start,
                requested_end=range_end,
                previous_start=previous_start,
                previous_end=previous_end,
                expected_days=period_days,
                covered_days=covered_days,
                missing_dates=missing_dates,
            ),
            comparison=comparison,
            coverage=coverage,
            insights=self._build_insights(summary, comparison, coverage, period_days),
            analysis=analysis,
        )

    @staticmethod
    def _summarize(metrics: list, promotion_metrics: list | None = None) -> SummaryMetric:
        paid_amount = sum((metric.paid_amount for metric in metrics), Decimal("0"))
        visitors = sum(metric.visitors for metric in metrics)
        buyers = sum(metric.buyers for metric in metrics)
        promotion_cost = sum((metric.promotion_cost for metric in metrics), Decimal("0"))
        refund_amount = sum((getattr(metric, "refund_amount", Decimal("0")) for metric in metrics), Decimal("0"))
        if promotion_metrics is None:
            promotion_plan_spend = sum((getattr(metric, "promotion_plan_spend", Decimal("0")) for metric in metrics), Decimal("0"))
            promotion_attributed_paid_amount = sum((getattr(metric, "promotion_attributed_paid_amount", Decimal("0")) for metric in metrics), Decimal("0"))
        else:
            promotion_plan_spend = sum((metric.spend for metric in promotion_metrics), Decimal("0"))
            promotion_attributed_paid_amount = sum((metric.paid_amount for metric in promotion_metrics), Decimal("0"))
        conversion_rate = Decimal(buyers) / Decimal(visitors) * Decimal("100") if visitors else Decimal("0")
        roi = paid_amount / promotion_cost if promotion_cost else Decimal("0")
        promotion_roi = promotion_attributed_paid_amount / promotion_plan_spend if promotion_plan_spend else Decimal("0")
        promotion_fee_ratio = promotion_plan_spend / paid_amount * Decimal("100") if paid_amount else Decimal("0")
        return SummaryMetric(
            paid_amount=paid_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            visitors=visitors,
            buyers=buyers,
            conversion_rate=conversion_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            promotion_cost=promotion_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            roi=roi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            average_daily_paid_amount=(paid_amount / len(metrics) if metrics else Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            customer_unit_price=(paid_amount / buyers if buyers else Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            refund_amount=refund_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            net_paid_amount=(paid_amount - refund_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            promotion_plan_spend=promotion_plan_spend.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            promotion_attributed_paid_amount=promotion_attributed_paid_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            promotion_roi=promotion_roi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            promotion_fee_ratio=promotion_fee_ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )

    @staticmethod
    def _compare(current: Decimal, previous: Decimal) -> ComparisonMetric:
        delta = current - previous
        change_percent = (delta / abs(previous) * Decimal("100")) if previous else None
        return ComparisonMetric(
            current=current,
            previous=previous,
            delta=delta,
            change_percent=change_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if change_percent is not None else None,
        )

    @staticmethod
    def _without_change_percent(comparison: SummaryComparison) -> SummaryComparison:
        def keep_values(metric: ComparisonMetric) -> ComparisonMetric:
            return ComparisonMetric(current=metric.current, previous=metric.previous, delta=metric.delta)

        return SummaryComparison(
            paid_amount=keep_values(comparison.paid_amount),
            visitors=keep_values(comparison.visitors),
            buyers=keep_values(comparison.buyers),
            conversion_rate=keep_values(comparison.conversion_rate),
            promotion_cost=keep_values(comparison.promotion_cost),
            customer_unit_price=keep_values(comparison.customer_unit_price) if comparison.customer_unit_price else None,
        )

    @staticmethod
    def _build_insights(
        summary: SummaryMetric,
        comparison: SummaryComparison,
        coverage: list[DataCoverage],
        expected_days: int,
    ) -> list[BusinessInsight]:
        insights: list[BusinessInsight] = []
        primary = next((item for item in coverage if item.dataset in {"店铺日概览", "店铺总览"}), None)
        if primary and primary.status != "complete":
            missing_count = len(primary.missing_dates)
            insights.append(
                BusinessInsight(
                    level="warning",
                    title="店铺日报缺失",
                    detail=f"已入库 {primary.covered_days}/{expected_days} 天；缺少 {missing_count} 天。",
                )
            )
        stale = [item for item in coverage if item.latest_date and primary and item.latest_date < primary.latest_date and item.dataset != primary.dataset]
        for item in stale[:3]:
            insights.append(
                BusinessInsight(
                    level="warning",
                    title=f"{item.dataset}未覆盖最新日",
                    detail=f"最新日期 {item.latest_date.isoformat()}；店铺日报最新 {primary.latest_date.isoformat()}。",
                )
            )
        paid_change = comparison.paid_amount.change_percent
        if paid_change is not None and abs(paid_change) >= Decimal("10"):
            direction = "上升" if paid_change > 0 else "下降"
            insights.append(
                BusinessInsight(
                    level="positive" if paid_change > 0 else "warning",
                    title=f"支付金额{direction} {abs(paid_change):.2f}%",
                    detail=f"本期 {summary.paid_amount:.2f}，上期 {comparison.paid_amount.previous:.2f}。",
                )
            )
        conversion_change = comparison.conversion_rate.change_percent
        if conversion_change is not None and conversion_change <= Decimal("-10"):
            insights.append(
                BusinessInsight(
                    level="warning",
                    title="支付转化率下降",
                    detail=f"本期 {summary.conversion_rate:.2f}%，环比下降 {abs(conversion_change):.2f}%。",
                )
            )
        if summary.promotion_plan_spend > 0 and summary.promotion_roi < Decimal("1"):
            insights.append(
                BusinessInsight(
                    level="warning",
                    title="推广 ROI 低于 1",
                    detail=f"推广花费 {summary.promotion_plan_spend:.2f}，ROI {summary.promotion_roi:.2f}。",
                )
            )
        if summary.promotion_fee_ratio >= Decimal("20"):
            insights.append(
                BusinessInsight(
                    level="warning",
                    title="推广费比偏高",
                    detail=f"推广花费占支付金额 {summary.promotion_fee_ratio:.2f}%。",
                )
            )
        if not insights:
            insights.append(
                BusinessInsight(
                    level="info",
                    title="暂无经营预警",
                    detail="店铺日报完整，核心指标未触发预警。",
                )
            )
        return insights
