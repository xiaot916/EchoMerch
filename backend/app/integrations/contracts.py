from datetime import date
from typing import Protocol

from app.modules.analytics.schemas import (
    DailyMetric,
    DataFreshness,
    ProductMetric,
    PromotionDailyMetric,
    PromotionMetric,
    TrafficMetric,
)


class AnalyticsSource(Protocol):
    def get_date_bounds(self) -> tuple[date, date]:
        """Return the available reporting range for the primary shop dataset."""

    @staticmethod
    def default_range(maximum: date) -> tuple[date, date]:
        """Return the default dashboard range ending at the latest available date."""

    def get_daily_metrics(self, start_date: date, end_date: date) -> list[DailyMetric]:
        """Return the normalized daily store-level metric series."""

    def get_top_products(self, start_date: date, end_date: date) -> list[ProductMetric]:
        """Return products ranked by paid amount."""

    def get_product_date_bounds(self) -> tuple[date, date]:
        """Return the available range for the product sales dataset."""

    def get_traffic_sources(self, start_date: date, end_date: date) -> list[TrafficMetric]:
        """Return first-level traffic sources ranked by paid amount."""

    def get_top_promotion_plans(self, start_date: date, end_date: date) -> list[PromotionMetric]:
        """Return paid promotion plans ranked by spend."""

    def get_promotion_daily_metrics(
        self,
        start_date: date,
        end_date: date,
    ) -> list[PromotionDailyMetric]:
        """Return complete daily promotion totals for the requested range."""

    def get_freshness(self) -> list[DataFreshness]:
        """Return the most recent date for each report currently shown in the UI."""
