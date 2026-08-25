from datetime import date
from decimal import Decimal

from app.modules.analytics.schemas import ComparisonMetric, DailyMetric, PromotionDailyMetric, SummaryComparison
from app.modules.analytics.service import AnalyticsService


def test_store_overview_uses_complete_promotion_totals_for_fee_ratio_and_roi() -> None:
    store_metrics = [
        DailyMetric(
            stat_date=date(2026, 8, 1),
            paid_amount=Decimal("1000"),
            visitors=100,
            buyers=10,
            conversion_rate=Decimal("10"),
            promotion_cost=Decimal("80"),
            refund_amount=Decimal("100"),
        )
    ]
    promotion_metrics = [
        PromotionDailyMetric(
            stat_date=date(2026, 8, 1),
            spend=Decimal("150"),
            paid_amount=Decimal("400"),
        ),
        PromotionDailyMetric(
            stat_date=date(2026, 8, 2),
            spend=Decimal("50"),
            paid_amount=Decimal("100"),
        ),
    ]

    summary = AnalyticsService._summarize(store_metrics, promotion_metrics)

    assert summary.paid_amount == Decimal("1000.00")
    assert summary.refund_amount == Decimal("100.00")
    assert summary.net_paid_amount == Decimal("900.00")
    assert summary.promotion_plan_spend == Decimal("200.00")
    assert summary.promotion_attributed_paid_amount == Decimal("500.00")
    assert summary.promotion_fee_ratio == Decimal("20.00")
    assert summary.promotion_roi == Decimal("2.50")


def test_incomplete_store_period_removes_change_percent() -> None:
    comparison = SummaryComparison(
        paid_amount=ComparisonMetric(current=Decimal("800"), previous=Decimal("1000"), delta=Decimal("-200"), change_percent=Decimal("-20")),
        visitors=ComparisonMetric(current=Decimal("80"), previous=Decimal("100"), delta=Decimal("-20"), change_percent=Decimal("-20")),
        buyers=ComparisonMetric(current=Decimal("8"), previous=Decimal("10"), delta=Decimal("-2"), change_percent=Decimal("-20")),
        conversion_rate=ComparisonMetric(current=Decimal("10"), previous=Decimal("10"), delta=Decimal("0"), change_percent=Decimal("0")),
        promotion_cost=ComparisonMetric(current=Decimal("60"), previous=Decimal("80"), delta=Decimal("-20"), change_percent=Decimal("-25")),
    )

    result = AnalyticsService._without_change_percent(comparison)

    assert result.paid_amount.change_percent is None
    assert result.visitors.change_percent is None
    assert result.buyers.change_percent is None
    assert result.conversion_rate.change_percent is None
    assert result.promotion_cost.change_percent is None
    assert result.paid_amount.current == Decimal("800")
    assert result.paid_amount.previous == Decimal("1000")
