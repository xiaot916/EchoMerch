from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.core.local_database import (
    BUSINESS_DAY,
    CRAWL_RUN_ID,
    CRAWL_TASK_TYPE,
    DAY_STATUS,
    STORE_ID,
    q,
)
from app.modules.analytics.schemas import (
    AnalysisDailyMetric,
    AnalysisSnapshot,
    BrandZoneAnalysis,
    BybtAnalysis,
    BybtDailyMetric,
    ContentAnalysis,
    ContentDailyMetric,
    CpsAnalysis,
    CpsDailyMetric,
    CustomerAnalysis,
    CustomerDailyMetric,
    CustomerSegmentMetric,
    CustomerServiceAccountMetric,
    CustomerServiceAnalysis,
    CustomerServiceDailyMetric,
    DailyMetric,
    DataCoverage,
    DataFreshness,
    FlashSaleAnalysisResponse,
    FlashSaleComparison,
    FlashSaleDailyMetric,
    FlashSaleSummary,
    LiveAnalysis,
    LiveDailyMetric,
    LiveTalentMetric,
    MemberAnalysis,
    MemberChannelMetric,
    MemberDailyMetric,
    NewCustomerDiscountAnalysis,
    NewCustomerDiscountDailyMetric,
    ProductMetric,
    ProductAnalysisDailyMetric,
    ProductAnalysisResponse,
    PromotionAnalysis,
    PromotionDailyMetric,
    PromotionDimensionMetric,
    PromotionLayerCoverage,
    PromotionMetric,
    PromotionProductListResponse,
    PromotionProductMetric,
    PromotionSceneMetric,
    PromotionSummaryMetric,
    PromotionWorkbenchResponse,
    ShoppingGoldAnalysis,
    ShoppingGoldDailyMetric,
    TrafficMetric,
    TrafficTreeNode,
    UtryAnalysisResponse,
    UtryDailyMetric,
    UtryProductMetric,
    UtryRepurchaseSnapshot,
    UtrySampleSummary,
)
from app.warehouse.store import WarehouseDataNotAvailable, WarehouseStore


# A successful report may legitimately contain no dimension rows. For these
# datasets, the crawl ledger is evidence that the date was checked, not missing.
_CRAWL_COVERAGE_TASKS = {
    "U先派样": "utry_overviews",
    "U先复购": "utry_overviews",
    "推广计划": "alimama_campaigns",
    "推广人群": "alimama_crowds",
    "推广单元": "alimama_adgroups",
    "推广关键词": "alimama_bidwords",
    "推广商品": "alimama_item_promotion",
    "推广内容": "alimama_content_promotion",
}


class LocalWarehouseAnalyticsRepository:
    """Read-only analytics adapter over locally ingested normalized data."""

    def __init__(self, database_path: Path, store_id: int | None = None) -> None:
        self._database_path = database_path
        self._warehouse = WarehouseStore(database_path)
        self._store_id = store_id if store_id is not None else self._resolve_store_id()

    def get_date_bounds(self) -> tuple[date, date]:
        return self._warehouse.get_date_bounds(store_id=self._store_id)

    @staticmethod
    def default_range(maximum: date) -> tuple[date, date]:
        return maximum - timedelta(days=6), maximum

    def get_daily_metrics(self, start_date: date, end_date: date) -> list[DailyMetric]:
        rows = self._rows(
            """
            select overview."业务日期" as business_day,
                   overview."支付金额" as paid_amount,
                   overview."访客数" as visitors,
                   overview."支付买家数" as buyers,
                   overview."支付转化率" as conversion_rate,
                   overview."全站推广花费" as promotion_cost,
                   overview."退款金额（支付时间）" as refund_amount,
                   overview."金额退款率" as refund_rate,
                   coalesce(promotion.spend, 0) as promotion_plan_spend,
                   coalesce(promotion.paid_amount, 0) as promotion_attributed_paid_amount
            from store_daily_overviews overview
            left join (
                select "店铺ID", "业务日期",
                       sum(cast(coalesce("花费", '0') as real)) as spend,
                       sum(cast(coalesce("总成交金额", '0') as real)) as paid_amount
                from store_daily_promotion_campaigns
                where "店铺ID" = ? and "业务日期" between ? and ?
                group by "店铺ID", "业务日期"
            ) promotion
              on promotion."店铺ID" = overview."店铺ID"
             and promotion."业务日期" = overview."业务日期"
            where overview."店铺ID" = ? and overview."业务日期" between ? and ?
            order by overview."业务日期"
            """,
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return [
            DailyMetric(
                stat_date=date.fromisoformat(row["business_day"]),
                paid_amount=_decimal(row["paid_amount"]),
                visitors=_integer(row["visitors"]),
                conversion_rate=(
                    _decimal(row["conversion_rate"])
                    or _percent_ratio(_integer(row["buyers"]), _integer(row["visitors"]))
                ),
                promotion_cost=_decimal(row["promotion_cost"]),
                buyers=_integer(row["buyers"]),
                refund_amount=_decimal(row.get("refund_amount")),
                refund_rate=_decimal(row.get("refund_rate")),
                promotion_plan_spend=_decimal(row.get("promotion_plan_spend")),
                promotion_attributed_paid_amount=_decimal(row.get("promotion_attributed_paid_amount")),
            )
            for row in rows
        ]

    def get_top_products(self, start_date: date, end_date: date) -> list[ProductMetric]:
        return self.get_products(start_date, end_date, limit=20)

    def get_products(
        self,
        start_date: date,
        end_date: date,
        *,
        limit: int | None = None,
    ) -> list[ProductMetric]:
        limit_clause = f"limit {int(limit)}" if limit is not None else ""
        rows = self._rows(
            f"""
            select
                rankings."商品ID" as product_id,
                max(rankings."商品名称") as product_name,
                sum(cast(coalesce(rankings."支付金额", '0') as real)) as paid_amount,
                sum(cast(coalesce(rankings."支付买家数", '0') as real)) as buyers,
                sum(cast(coalesce(rankings."商品访客数", '0') as real)) as visitors,
                sum(cast(coalesce(rankings."商品加购人数", '0') as real)) as add_cart_users,
                sum(cast(coalesce(rankings."商品收藏人数", '0') as real)) as favorite_users,
                sum(cast(coalesce(rankings."商品浏览量", '0') as real)) as page_views,
                sum(cast(coalesce(rankings."搜索引导访客数", '0') as real)) as search_visitors,
                sum(cast(coalesce(rankings."推广消耗", '0') as real)) as promotion_spend,
                max(coalesce(nullif(catalog."类型", ''), '未分类')) as product_type,
                max(coalesce(nullif(catalog."系列", ''), '未分类')) as series,
                max(coalesce(nullif(catalog."定位", ''), '未分类')) as positioning
            from store_daily_product_rankings rankings
            left join store_product_catalog catalog
              on catalog."店铺ID" = rankings."店铺ID" and catalog."商品ID" = rankings."商品ID"
            where rankings."店铺ID" = ? and rankings."业务日期" between ? and ?
            group by rankings."商品ID"
            order by paid_amount desc
            {limit_clause}
            """,
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return [
            ProductMetric(
                product_id=str(row["product_id"] or ""),
                product_name=str(row["product_name"] or "未命名商品"),
                paid_amount=_decimal(row["paid_amount"]),
                buyers=_integer(row["buyers"]),
                visitors=_integer(row["visitors"]),
                add_cart_users=_integer(row["add_cart_users"]),
                favorite_users=_integer(row["favorite_users"]),
                page_views=_integer(row["page_views"]),
                search_visitors=_integer(row["search_visitors"]),
                promotion_spend=_decimal(row["promotion_spend"]),
                product_type=str(row["product_type"] or "未分类"),
                series=str(row["series"] or "未分类"),
                positioning=str(row["positioning"] or "未分类"),
            )
            for row in rows
        ]

    def get_product_analysis(
        self,
        start_date: date,
        end_date: date,
        product_id: str | None = None,
    ) -> ProductAnalysisResponse:
        products = self.get_products(start_date, end_date)
        selected = next((item for item in products if item.product_id == product_id), None) if product_id else (products[0] if products else None)
        if selected is None:
            return ProductAnalysisResponse(range_start=start_date, range_end=end_date, products=products)

        daily_rows = self._rows(
            """
            select
                "业务日期" as business_day,
                sum(cast(coalesce("支付金额", '0') as real)) as paid_amount,
                sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
                sum(cast(coalesce("商品访客数", '0') as real)) as visitors,
                sum(cast(coalesce("商品加购人数", '0') as real)) as add_cart_users,
                sum(cast(coalesce("商品收藏人数", '0') as real)) as favorite_users,
                sum(cast(coalesce("推广消耗", '0') as real)) as promotion_spend
            from store_daily_product_rankings
            where "店铺ID" = ? and "商品ID" = ? and "业务日期" between ? and ?
            group by "业务日期"
            order by "业务日期"
            """,
            self._store_id,
            selected.product_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        daily_metrics = [
            ProductAnalysisDailyMetric(
                stat_date=date.fromisoformat(str(row["business_day"])),
                paid_amount=_decimal(row["paid_amount"]),
                buyers=_integer(row["buyers"]),
                visitors=_integer(row["visitors"]),
                add_cart_users=_integer(row["add_cart_users"]),
                favorite_users=_integer(row["favorite_users"]),
                promotion_spend=_decimal(row["promotion_spend"]),
                conversion_rate=_percent_ratio(_integer(row["buyers"]), _integer(row["visitors"])),
            )
            for row in daily_rows
        ]
        peers = [item for item in products if item.series == selected.series]
        return ProductAnalysisResponse(
            range_start=start_date,
            range_end=end_date,
            products=products,
            product=selected,
            daily_metrics=daily_metrics,
            peers=peers,
        )

    def get_data_coverage(self, start_date: date, end_date: date) -> list[DataCoverage]:
        """Return date coverage for every dataset exposed by the dashboard."""
        expected_days = (end_date - start_date).days + 1
        coverage: list[DataCoverage] = []
        for label, table in self._dataset_tables():
            bounds = self._rows(
                f'''select min("业务日期") as first_date, max("业务日期") as latest_date
                    from {table} where "店铺ID" = ?''',
                self._store_id,
            )
            dates = self._rows(
                f'''select distinct "业务日期" as business_day from {table}
                    where "店铺ID" = ? and "业务日期" between ? and ?''',
                self._store_id,
                start_date.isoformat(),
                end_date.isoformat(),
            )
            available = {
                date.fromisoformat(str(row["business_day"]))
                for row in dates
                if row["business_day"]
            }
            confirmed_empty_days = self._successful_empty_report_days(
                label=label,
                start_date=start_date,
                end_date=end_date,
            )
            # A successful empty crawl is only "platform has no data" when
            # the normalized table truly has no row for that day.  If a later
            # or duplicate ingestion produced rows, physical data wins and
            # the day must not be reported as both covered and no-data.
            confirmed_no_data_days = confirmed_empty_days - available
            available.update(confirmed_no_data_days)
            missing = [
                start_date + timedelta(days=offset)
                for offset in range(expected_days)
                if start_date + timedelta(days=offset) not in available
            ]
            first_date = bounds[0]["first_date"] if bounds and bounds[0]["first_date"] else None
            latest_date = bounds[0]["latest_date"] if bounds and bounds[0]["latest_date"] else None
            if confirmed_no_data_days:
                confirmed_first = min(confirmed_no_data_days).isoformat()
                confirmed_latest = max(confirmed_no_data_days).isoformat()
                first_date = min(str(first_date), confirmed_first) if first_date else confirmed_first
                latest_date = max(str(latest_date), confirmed_latest) if latest_date else confirmed_latest
            coverage.append(
                DataCoverage(
                    dataset=label,
                    first_date=date.fromisoformat(str(first_date)) if first_date else None,
                    latest_date=date.fromisoformat(str(latest_date)) if latest_date else None,
                    expected_days=expected_days,
                    covered_days=len(available),
                    missing_dates=missing,
                    no_data_dates=sorted(confirmed_no_data_days),
                    status="empty" if not available else "complete" if not missing else "partial",
                )
            )
        return coverage

    def get_utry_analysis(self, start_date: date, end_date: date) -> UtryAnalysisResponse:
        """Build the U先 sample-to-repurchase workbench from full local facts.

        Sample metrics are additive over the selected range. Repurchase metrics
        are rolling snapshots, so the current summary intentionally uses only
        the latest available business day and the daily series only compares
        snapshots day by day.
        """
        expected_days = (end_date - start_date).days + 1
        coverage = self.get_data_coverage(start_date, end_date)
        sample_coverage = next((item for item in coverage if item.dataset == "U先派样"), None)
        repurchase_coverage = next((item for item in coverage if item.dataset == "U先复购"), None)

        sample_rows = self._rows(
            '''select "业务日期" as business_day,
                      sum(cast(coalesce("派样人次", '0') as real)) as sample_people,
                      sum(cast(coalesce("派样单量", '0') as real)) as sample_orders,
                      sum(cast(coalesce("派样GMV", '0') as real)) as sample_gmv,
                      sum(cast(coalesce("派样180天商家新客数", '0') as real)) as merchant_new_customers_180d,
                      sum(cast(coalesce("派样365天商家新客数", '0') as real)) as merchant_new_customers_365d,
                      sum(cast(coalesce("新会员数", '0') as real)) as new_members,
                      sum(cast(coalesce("新粉丝数", '0') as real)) as new_followers
               from store_daily_utry_sample_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               group by "业务日期" order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        sample_by_day = {str(row["business_day"]): row for row in sample_rows if row.get("business_day")}
        sample_complete_days = set(sample_by_day)
        sample_no_data_days = {item.isoformat() for item in (sample_coverage.no_data_dates if sample_coverage else [])}

        rep_rows = self._rows(
            '''select "业务日期" as business_day,
                      sum(cast(coalesce("同店30日回购金额", '0') as real)) as store_30d_repurchase_amount,
                      sum(cast(coalesce("同店90日回购金额", '0') as real)) as store_90d_repurchase_amount,
                      sum(cast(coalesce("同店365日回购金额", '0') as real)) as store_365d_repurchase_amount
               from store_daily_utry_repurchase_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               group by "业务日期" order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        rep_by_day = {str(row["business_day"]): row for row in rep_rows if row.get("business_day")}
        rep_complete_days = set(rep_by_day)
        rep_no_data_days = {item.isoformat() for item in (repurchase_coverage.no_data_dates if repurchase_coverage else [])}

        def number_or_none(value: object) -> int | None:
            return None if value is None or value == "" else _integer(value)

        def decimal_or_none(value: object) -> Decimal | None:
            return None if value is None or value == "" else _decimal(value)

        daily_metrics: list[UtryDailyMetric] = []
        for offset in range(expected_days):
            current_day = start_date + timedelta(days=offset)
            key = current_day.isoformat()
            sample = sample_by_day.get(key)
            repurchase = rep_by_day.get(key)
            daily_metrics.append(UtryDailyMetric(
                stat_date=current_day,
                sample_status="complete" if key in sample_complete_days else "no_data" if key in sample_no_data_days else "missing",
                repurchase_status="complete" if key in rep_complete_days else "no_data" if key in rep_no_data_days else "missing",
                sample_people=number_or_none(sample.get("sample_people")) if sample else None,
                sample_orders=number_or_none(sample.get("sample_orders")) if sample else None,
                sample_gmv=decimal_or_none(sample.get("sample_gmv")) if sample else None,
                merchant_new_customers_180d=number_or_none(sample.get("merchant_new_customers_180d")) if sample else None,
                merchant_new_customers_365d=number_or_none(sample.get("merchant_new_customers_365d")) if sample else None,
                new_members=number_or_none(sample.get("new_members")) if sample else None,
                new_followers=number_or_none(sample.get("new_followers")) if sample else None,
                store_30d_repurchase_amount=decimal_or_none(repurchase.get("store_30d_repurchase_amount")) if repurchase else None,
                store_90d_repurchase_amount=decimal_or_none(repurchase.get("store_90d_repurchase_amount")) if repurchase else None,
                store_365d_repurchase_amount=decimal_or_none(repurchase.get("store_365d_repurchase_amount")) if repurchase else None,
            ))

        def sample_total(name: str) -> int:
            return sum(_integer(row.get(name)) for row in sample_rows)

        sample_people = sample_total("sample_people")
        sample_orders = sample_total("sample_orders")
        sample_gmv = sum((_decimal(row.get("sample_gmv")) for row in sample_rows), Decimal("0"))
        sample_summary = UtrySampleSummary(
            sample_people=sample_people,
            sample_orders=sample_orders,
            sample_gmv=sample_gmv,
            merchant_new_customers_180d=sample_total("merchant_new_customers_180d"),
            merchant_new_customers_365d=sample_total("merchant_new_customers_365d"),
            new_members=sample_total("new_members"),
            new_followers=sample_total("new_followers"),
            average_orders_per_person=Decimal(sample_orders) / Decimal(sample_people) if sample_people else Decimal("0"),
            sample_gmv_per_person=sample_gmv / Decimal(sample_people) if sample_people else Decimal("0"),
            merchant_new_customer_rate_180d=_percent_ratio(sample_total("merchant_new_customers_180d"), sample_people) if sample_people else None,
            merchant_new_customer_rate_365d=_percent_ratio(sample_total("merchant_new_customers_365d"), sample_people) if sample_people else None,
        )

        rep_days = self._rows(
            '''select distinct "业务日期" as business_day
               from store_daily_utry_repurchase_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        latest_repurchase_day = str(rep_days[-1]["business_day"]) if rep_days else None
        previous_repurchase_day = str(rep_days[-2]["business_day"]) if len(rep_days) > 1 else None

        def snapshot(day_value: str | None) -> UtryRepurchaseSnapshot:
            if not day_value:
                return UtryRepurchaseSnapshot()
            rows = self._rows(
                '''select count(*) as product_count,
                          sum(case when trim(coalesce("是否绑定正装", '')) in ('1','是','true','TRUE','yes','Y') then 1 else 0 end) as bound_regular_product_count,
                          sum(case when trim(coalesce("是否配置回购券", '')) in ('1','是','true','TRUE','yes','Y') then 1 else 0 end) as configured_coupon_count,
                          sum(case when trim(coalesce("是否配置回购礼金", '')) in ('1','是','true','TRUE','yes','Y') then 1 else 0 end) as configured_gift_count,
                          sum(cast(coalesce("同店30日回购UV", '0') as real)) as store_30d_repurchase_uv,
                          sum(cast(coalesce("同店30日回购金额", '0') as real)) as store_30d_repurchase_amount,
                          sum(cast(coalesce("同店90日回购UV", '0') as real)) as store_90d_repurchase_uv,
                          sum(cast(coalesce("同店90日回购金额", '0') as real)) as store_90d_repurchase_amount,
                          sum(cast(coalesce("同店365日回购UV", '0') as real)) as store_365d_repurchase_uv,
                          sum(cast(coalesce("同店365日回购金额", '0') as real)) as store_365d_repurchase_amount,
                          sum(cast(coalesce("同品牌365日回购UV", '0') as real)) as brand_365d_repurchase_uv,
                          sum(cast(coalesce("同品牌365日回购金额", '0') as real)) as brand_365d_repurchase_amount
                   from store_daily_utry_repurchase_overviews
                   where "店铺ID" = ? and "业务日期" = ?''',
                self._store_id, day_value,
            )
            row = rows[0] if rows else {}
            product_count = _integer(row.get("product_count"))
            bound = _integer(row.get("bound_regular_product_count"))
            coupon = _integer(row.get("configured_coupon_count"))
            gift = _integer(row.get("configured_gift_count"))
            return UtryRepurchaseSnapshot(
                business_day=date.fromisoformat(day_value),
                product_count=product_count,
                bound_regular_product_count=bound,
                configured_coupon_count=coupon,
                configured_gift_count=gift,
                bound_regular_product_share=_percent_ratio(bound, product_count) if product_count else None,
                configured_coupon_share=_percent_ratio(coupon, product_count) if product_count else None,
                configured_gift_share=_percent_ratio(gift, product_count) if product_count else None,
                store_30d_repurchase_uv=_integer(row.get("store_30d_repurchase_uv")),
                store_30d_repurchase_amount=_decimal(row.get("store_30d_repurchase_amount")),
                store_90d_repurchase_uv=_integer(row.get("store_90d_repurchase_uv")),
                store_90d_repurchase_amount=_decimal(row.get("store_90d_repurchase_amount")),
                store_365d_repurchase_uv=_integer(row.get("store_365d_repurchase_uv")),
                store_365d_repurchase_amount=_decimal(row.get("store_365d_repurchase_amount")),
                brand_365d_repurchase_uv=_integer(row.get("brand_365d_repurchase_uv")),
                brand_365d_repurchase_amount=_decimal(row.get("brand_365d_repurchase_amount")),
            )

        latest_repurchase = snapshot(latest_repurchase_day)
        previous_repurchase = snapshot(previous_repurchase_day)
        product_sample_rows = self._rows(
            '''select cast("商品ID" as text) as product_id, max("商品标题") as product_name,
                      sum(cast(coalesce("派样人次", '0') as real)) as sample_people,
                      sum(cast(coalesce("派样单量", '0') as real)) as sample_orders,
                      sum(cast(coalesce("派样GMV", '0') as real)) as sample_gmv,
                      sum(cast(coalesce("派样180天商家新客数", '0') as real)) as merchant_new_customers_180d,
                      sum(cast(coalesce("派样365天商家新客数", '0') as real)) as merchant_new_customers_365d,
                      sum(cast(coalesce("新会员数", '0') as real)) as new_members,
                      sum(cast(coalesce("新粉丝数", '0') as real)) as new_followers,
                      max("叶子类目名称") as leaf_category
               from store_daily_utry_sample_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               group by cast("商品ID" as text)''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        product_rep_rows = self._rows(
            '''select cast("商品ID" as text) as product_id, max("商品名称") as product_name,
                      sum(cast(coalesce("同店30日回购UV", '0') as real)) as store_30d_repurchase_uv,
                      sum(cast(coalesce("同店30日回购金额", '0') as real)) as store_30d_repurchase_amount,
                      sum(cast(coalesce("同店90日回购UV", '0') as real)) as store_90d_repurchase_uv,
                      sum(cast(coalesce("同店90日回购金额", '0') as real)) as store_90d_repurchase_amount,
                      sum(cast(coalesce("同店365日回购UV", '0') as real)) as store_365d_repurchase_uv,
                      sum(cast(coalesce("同店365日回购金额", '0') as real)) as store_365d_repurchase_amount,
                      sum(cast(coalesce("同品牌365日回购金额", '0') as real)) as brand_365d_repurchase_amount,
                      max("叶子类目") as leaf_category,
                      max("是否绑定正装") as bind_regular_product,
                      max("是否配置回购券") as configured_repurchase_coupon,
                      max("是否配置回购礼金") as configured_repurchase_gift
               from store_daily_utry_repurchase_overviews
               where "店铺ID" = ? and "业务日期" = ?
               group by cast("商品ID" as text)''',
            self._store_id, latest_repurchase_day or end_date.isoformat(),
        )
        sample_by_product = {str(row["product_id"]): row for row in product_sample_rows if row.get("product_id")}
        rep_by_product = {str(row["product_id"]): row for row in product_rep_rows if row.get("product_id")}
        products: list[UtryProductMetric] = []
        for product_id in sorted(set(sample_by_product) | set(rep_by_product)):
            sample = sample_by_product.get(product_id, {})
            rep = rep_by_product.get(product_id, {})
            sample_people_value = _integer(sample.get("sample_people"))
            repurchase_amount = _decimal(rep.get("store_365d_repurchase_amount")) if rep else Decimal("0")
            if sample_people_value >= 50 and repurchase_amount == 0:
                tag = "高派样低回购"
            elif sample_people_value >= 50 and _integer(sample.get("merchant_new_customers_180d")) == 0:
                tag = "高派样低新客"
            elif sample_people_value < 50 and repurchase_amount > 0:
                tag = "低派样高回购"
            elif rep and str(rep.get("bind_regular_product") or "") not in {"1", "是", "true", "TRUE", "yes", "Y"}:
                tag = "未绑定正装"
            elif rep and str(rep.get("configured_repurchase_coupon") or "") not in {"1", "是", "true", "TRUE", "yes", "Y"}:
                tag = "待配置回购权益"
            else:
                tag = "持续观察"
            products.append(UtryProductMetric(
                product_id=product_id,
                product_name=str(sample.get("product_name") or rep.get("product_name") or ""),
                sample_people=number_or_none(sample.get("sample_people")) if sample else None,
                sample_orders=number_or_none(sample.get("sample_orders")) if sample else None,
                sample_gmv=decimal_or_none(sample.get("sample_gmv")) if sample else None,
                merchant_new_customers_180d=number_or_none(sample.get("merchant_new_customers_180d")) if sample else None,
                merchant_new_customers_365d=number_or_none(sample.get("merchant_new_customers_365d")) if sample else None,
                new_members=number_or_none(sample.get("new_members")) if sample else None,
                new_followers=number_or_none(sample.get("new_followers")) if sample else None,
                store_30d_repurchase_uv=number_or_none(rep.get("store_30d_repurchase_uv")) if rep else None,
                store_30d_repurchase_amount=decimal_or_none(rep.get("store_30d_repurchase_amount")) if rep else None,
                store_90d_repurchase_uv=number_or_none(rep.get("store_90d_repurchase_uv")) if rep else None,
                store_90d_repurchase_amount=decimal_or_none(rep.get("store_90d_repurchase_amount")) if rep else None,
                store_365d_repurchase_uv=number_or_none(rep.get("store_365d_repurchase_uv")) if rep else None,
                store_365d_repurchase_amount=decimal_or_none(rep.get("store_365d_repurchase_amount")) if rep else None,
                brand_365d_repurchase_amount=decimal_or_none(rep.get("brand_365d_repurchase_amount")) if rep else None,
                leaf_category=str(sample.get("leaf_category") or rep.get("leaf_category") or ""),
                bind_regular_product=str(rep.get("bind_regular_product") or "") if rep else "",
                configured_repurchase_coupon=str(rep.get("configured_repurchase_coupon") or "") if rep else "",
                configured_repurchase_gift=str(rep.get("configured_repurchase_gift") or "") if rep else "",
                diagnostic_tag=tag,
            ))
        products.sort(key=lambda item: (item.sample_gmv or Decimal("0")), reverse=True)

        warnings = [
            "派样汇总使用所选区间所有有效业务日；缺失日期和平台无数据日期不按 0 参与。",
            "回购 30/90/365 日指标是最新业务日的滚动快照，趋势逐日比较，不能跨日累加。",
            "当前没有与首批派样 cohort 严格对应的回购分母，页面不计算 U先回购率。",
            "U先成交与回购金额为平台归因/快照口径，没有实验或对照时不代表因果增量。",
        ]
        return UtryAnalysisResponse(
            range_start=start_date,
            range_end=end_date,
            latest_sample_date=max(sample_complete_days) if sample_complete_days else None,
            latest_repurchase_date=date.fromisoformat(latest_repurchase_day) if latest_repurchase_day else None,
            sample_summary=sample_summary,
            latest_repurchase=latest_repurchase,
            previous_repurchase=previous_repurchase,
            daily_metrics=daily_metrics,
            products=products,
            sample_coverage=sample_coverage,
            repurchase_coverage=repurchase_coverage,
            warnings=warnings,
        )

    def _successful_empty_report_days(
        self,
        *,
        label: str,
        start_date: date,
        end_date: date,
    ) -> set[date]:
        task_type = _CRAWL_COVERAGE_TASKS.get(label)
        if task_type is None:
            return set()

        rows = self._rows(
            f"""
            select distinct days.{q(BUSINESS_DAY)} as business_day
            from crawl_run_days as days
            inner join crawl_runs as runs
              on runs.{q(CRAWL_RUN_ID)} = days.{q(CRAWL_RUN_ID)}
            where days.{q(STORE_ID)} = ?
              and runs.{q(CRAWL_TASK_TYPE)} = ?
              and days.{q(DAY_STATUS)} in ('ingested', 'no_data')
              and days.{q(BUSINESS_DAY)} between ? and ?
            """,
            self._store_id,
            task_type,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return {
            date.fromisoformat(str(row["business_day"]))
            for row in rows
            if row["business_day"]
        }

    def get_product_date_bounds(self) -> tuple[date, date]:
        rows = self._rows(
            """
            select min("业务日期") as minimum_date, max("业务日期") as maximum_date
            from store_daily_product_rankings
            where "店铺ID" = ?
            """,
            self._store_id,
        )
        if not rows or not rows[0]["maximum_date"]:
            raise WarehouseDataNotAvailable("The local product ranking report contains no data.")
        return date.fromisoformat(str(rows[0]["minimum_date"])), date.fromisoformat(str(rows[0]["maximum_date"]))

    def get_traffic_sources(self, start_date: date, end_date: date) -> list[TrafficMetric]:
        rows = self._rows(
            """
            select
                "一级来源" as source_name,
                sum(cast("访客数" as real)) as visitors,
                sum(cast("新访客数" as real)) as new_visitors,
                sum(cast("加购人数" as real)) as add_cart_users,
                sum(cast("商品收藏人数" as real)) as favorite_users,
                sum(cast("支付金额" as real)) as paid_amount,
                sum(cast("支付买家数" as real)) as buyers
            from store_daily_traffic_sources
            where "店铺ID" = ?
              and "业务日期" between ? and ?
              and "来源层级" = 1
            group by "一级来源"
            order by paid_amount desc
            """,
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return [
            TrafficMetric(
                source_name=str(row["source_name"] or "未分类"),
                visitors=_integer(row["visitors"]),
                paid_amount=_decimal(row["paid_amount"]),
                buyers=_integer(row["buyers"]),
                new_visitors=_integer(row["new_visitors"]),
                add_cart_users=_integer(row["add_cart_users"]),
                favorite_users=_integer(row["favorite_users"]),
                conversion_rate=_percent_ratio(_integer(row["buyers"]), _integer(row["visitors"])),
                uv_value=_decimal(row["paid_amount"]) / _integer(row["visitors"]) if _integer(row["visitors"]) else Decimal("0"),
            )
            for row in rows
        ]

    def get_traffic_tree(self, start_date: date, end_date: date) -> list[TrafficTreeNode]:
        """Return the source hierarchy using the report's native 1/2/3 levels.

        Parent and child rows are kept as separate attribution measures. They
        must not be added together because the platform can attribute one
        order to more than one source level.
        """
        rows = self._rows(
            """
            select
                "来源层级" as source_level,
                coalesce(nullif(trim("一级来源"), ''), '未分类') as level_1,
                coalesce(nullif(trim("二级来源"), ''), '未分类') as level_2,
                coalesce(nullif(trim("三级来源"), ''), '未分类') as level_3,
                sum(cast(coalesce("访客数", '0') as real)) as visitors,
                sum(cast(coalesce("新访客数", '0') as real)) as new_visitors,
                sum(cast(coalesce("加购人数", '0') as real)) as add_cart_users,
                sum(cast(coalesce("商品收藏人数", '0') as real)) as favorite_users,
                sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
                sum(cast(coalesce("支付金额", '0') as real)) as paid_amount
            from store_daily_traffic_sources
            where "店铺ID" = ? and "业务日期" between ? and ?
            group by "来源层级", "一级来源", "二级来源", "三级来源"
            order by "来源层级", paid_amount desc
            """,
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )

        metrics: dict[tuple[int, str, str, str], dict[str, object]] = {}
        for row in rows:
            level = max(1, min(3, _integer(row["source_level"])))
            path = (
                str(row["level_1"] or "未分类"),
                str(row["level_2"] or "未分类") if level >= 2 else "",
                str(row["level_3"] or "未分类") if level >= 3 else "",
            )
            metrics[(level, *path)] = row

        def metric(row: dict[str, object] | None) -> dict[str, object]:
            if row is None:
                return {
                    "visitors": 0,
                    "new_visitors": 0,
                    "add_cart_users": 0,
                    "favorite_users": 0,
                    "buyers": 0,
                    "paid_amount": Decimal("0"),
                }
            return {
                "visitors": _integer(row["visitors"]),
                "new_visitors": _integer(row["new_visitors"]),
                "add_cart_users": _integer(row["add_cart_users"]),
                "favorite_users": _integer(row["favorite_users"]),
                "buyers": _integer(row["buyers"]),
                "paid_amount": _decimal(row["paid_amount"]),
            }

        def make_node(level: int, path: tuple[str, str, str], parent_id: str | None) -> TrafficTreeNode:
            node_id = f"traffic-{level}-{'|'.join(path[:level])}"
            row = metrics.get((level, *path))
            values = metric(row)
            child_paths: set[tuple[str, str, str]] = set()
            if level < 3:
                for child_level, *child_path_values in metrics:
                    child_path = tuple(child_path_values)
                    if child_level != level + 1:
                        continue
                    if child_path[:level] == path[:level]:
                        child_paths.add(child_path)
            children = [
                make_node(level + 1, child_path, node_id)
                for child_path in sorted(child_paths, key=lambda item: str(item[level]))
            ]
            if row is None and children:
                values = {
                    key: sum((getattr(child, key) for child in children), Decimal("0") if key == "paid_amount" else 0)
                    for key in values
                }
            visitors = int(values["visitors"])
            buyers = int(values["buyers"])
            paid_amount = Decimal(values["paid_amount"])
            return TrafficTreeNode(
                id=node_id,
                parent_id=parent_id,
                level=level,
                name=path[level - 1],
                path=list(path[:level]),
                visitors=visitors,
                paid_amount=paid_amount,
                buyers=buyers,
                new_visitors=int(values["new_visitors"]),
                add_cart_users=int(values["add_cart_users"]),
                favorite_users=int(values["favorite_users"]),
                conversion_rate=_percent_ratio(buyers, visitors),
                uv_value=paid_amount / visitors if visitors else Decimal("0"),
                derived_from_children=row is None and bool(children),
                children=children,
            )

        root_paths = sorted(
            {
                tuple(path_values)
                for level, *path_values in metrics
                if level == 1
            },
            key=lambda item: str(item[0]),
        )
        return [make_node(1, path, None) for path in root_paths]

    def get_top_promotion_plans(
        self,
        start_date: date,
        end_date: date,
    ) -> list[PromotionMetric]:
        plan_rows = self._rows(
            """
            select
                coalesce(nullif("推广计划名称", ''), '未命名计划') as plan_name,
                coalesce(nullif("推广场景", ''), '未分类场景') as scene_name,
                sum(cast(coalesce("花费", '0') as real)) as spend,
                sum(cast(coalesce("总成交金额", '0') as real)) as paid_amount,
                sum(cast(coalesce("成交人数", '0') as real)) as buyers
            from store_daily_promotion_campaigns
            where "店铺ID" = ? and "业务日期" between ? and ?
            group by "推广计划ID", "推广计划名称", "推广场景"
            having sum(cast(coalesce("花费", '0') as real)) > 0
            order by spend desc
            """,
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        if plan_rows:
            return [
                PromotionMetric(
                    plan_name=str(row["plan_name"]),
                    scene_name=str(row["scene_name"]),
                    spend=_decimal(row["spend"]),
                    paid_amount=_decimal(row["paid_amount"]),
                    buyers=_integer(row["buyers"]),
                )
                for row in plan_rows
            ]

        rows = self._rows(
            """
            select
                sum(cast("全站推广花费" as real)) as all_site_promotion_spend,
                sum(cast("关键词推广花费" as real)) as keyword_promotion_spend,
                sum(cast("精准人群推广花费" as real)) as precision_audience_promotion_spend,
                sum(cast("智能场景花费" as real)) as smart_scene_spend,
                sum(cast("淘宝客佣金" as real)) as taoke_commission
            from store_daily_overviews
            where "店铺ID" = ? and "业务日期" between ? and ?
            """,
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        if not rows:
            return []
        row = rows[0]
        channels = [
            ("全站推广", row["all_site_promotion_spend"]),
            ("关键词推广", row["keyword_promotion_spend"]),
            ("精准人群推广", row["precision_audience_promotion_spend"]),
            ("智能场景", row["smart_scene_spend"]),
            ("淘宝客", row["taoke_commission"]),
        ]
        return [
            PromotionMetric(plan_name=name, spend=_decimal(value))
            for name, value in channels
            if value is not None and Decimal(str(value)) > 0
        ]

    def get_promotion_scenes(
        self,
        start_date: date,
        end_date: date,
    ) -> list[PromotionSceneMetric]:
        rows = self._rows(
            """
            select
                coalesce(nullif("推广场景", ''), '未分类场景') as scene_name,
                count(distinct "推广计划ID") as campaign_count,
                sum(cast(coalesce("花费", '0') as real)) as spend,
                sum(cast(coalesce("总成交金额", '0') as real)) as paid_amount,
                sum(cast(coalesce("成交人数", '0') as real)) as buyers
            from store_daily_promotion_campaigns
            where "店铺ID" = ? and "业务日期" between ? and ?
            group by "推广场景"
            having sum(cast(coalesce("花费", '0') as real)) > 0
            order by spend desc, scene_name
            """,
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return [
            PromotionSceneMetric(
                scene_name=str(row["scene_name"]),
                campaign_count=_integer(row["campaign_count"]),
                spend=_decimal(row["spend"]),
                paid_amount=_decimal(row["paid_amount"]),
                buyers=_integer(row["buyers"]),
            )
            for row in rows
        ]

    def get_promotion_daily_metrics(
        self,
        start_date: date,
        end_date: date,
    ) -> list[PromotionDailyMetric]:
        rows = self._rows(
            '''select "业务日期" as stat_date,
                sum(cast(coalesce("展现量", '0') as real)) as impressions,
                sum(cast(coalesce("点击量", '0') as real)) as clicks,
                sum(cast(coalesce("花费", '0') as real)) as spend,
                sum(cast(coalesce("总成交金额", '0') as real)) as paid_amount,
                sum(cast(coalesce("总成交笔数", '0') as real)) as orders,
                sum(cast(coalesce("成交人数", '0') as real)) as buyers,
                sum(cast(coalesce("总购物车数", '0') as real)) as carts,
                sum(cast(coalesce("成交新客数", '0') as real)) as new_buyers
               from store_daily_promotion_campaigns
               where "店铺ID" = ? and "业务日期" between ? and ?
               group by "业务日期" order by "业务日期"''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return [
            PromotionDailyMetric(
                stat_date=date.fromisoformat(str(row["stat_date"])),
                impressions=_integer(row["impressions"]),
                clicks=_integer(row["clicks"]),
                spend=_decimal(row["spend"]),
                paid_amount=_decimal(row["paid_amount"]),
                orders=_integer(row["orders"]),
                buyers=_integer(row["buyers"]),
                carts=_integer(row["carts"]),
                new_buyers=_integer(row["new_buyers"]),
            )
            for row in rows
        ]

    def get_promotion_workbench(
        self,
        start_date: date,
        end_date: date,
    ) -> PromotionWorkbenchResponse:
        """Return the full promotion hierarchy for diagnosis.

        Display layers may truncate rows, but this repository method never does:
        totals and model inputs must keep their full denominator.
        """
        where = (self._store_id, start_date.isoformat(), end_date.isoformat())
        summary_rows = self._rows(
            '''select count(distinct "推广计划ID") as campaign_count,
                sum(cast(coalesce("展现量", '0') as real)) as impressions,
                sum(cast(coalesce("点击量", '0') as real)) as clicks,
                sum(cast(coalesce("花费", '0') as real)) as spend,
                sum(cast(coalesce("总成交金额", '0') as real)) as paid_amount,
                sum(cast(coalesce("直接成交金额", '0') as real)) as direct_paid_amount,
                sum(cast(coalesce("间接成交金额", '0') as real)) as indirect_paid_amount,
                sum(cast(coalesce("总成交笔数", '0') as real)) as orders,
                sum(cast(coalesce("成交人数", '0') as real)) as buyers,
                sum(cast(coalesce("总购物车数", '0') as real)) as carts,
                sum(cast(coalesce("总收藏数", '0') as real)) as favorites,
                sum(cast(coalesce("成交新客数", '0') as real)) as new_buyers,
                sum(cast(coalesce("会员成交金额", '0') as real)) as member_paid_amount
               from store_daily_promotion_campaigns
               where "店铺ID" = ? and "业务日期" between ? and ?''',
            *where,
        )
        summary_row = summary_rows[0] if summary_rows else {}
        summary = self._promotion_summary(summary_row)
        daily = self.get_promotion_daily_metrics(start_date, end_date)
        scenes = self._promotion_dimension_rows(
            "store_daily_promotion_campaigns", '"推广场景"', '"推广场景"', where,
            scene_expr='"推广场景"',
            group_exprs=('"推广场景"',),
        )
        campaigns = self._promotion_dimension_rows(
            "store_daily_promotion_campaigns", '"推广计划ID"', '"推广计划名称"', where,
            scene_expr='"推广场景"', group_exprs=('"推广计划ID"', '"推广计划名称"', '"推广场景"'),
        )
        adgroups = self._promotion_dimension_rows(
            "store_daily_promotion_adgroups", '"推广单元ID"', '"推广单元名称"', where,
            scene_expr='"推广场景"', parent_id_expr='"推广计划ID"', parent_name_expr='"推广计划名称"',
            subject_id_expr='"商品ID"', subject_name_expr='"商品名称"', group_exprs=('"推广单元ID"', '"推广单元名称"', '"推广场景"', '"推广计划ID"', '"推广计划名称"', '"商品ID"', '"商品名称"'),
            has_direct=False, has_new=False, has_member=False,
        )
        audiences = self._promotion_dimension_rows(
            "store_daily_promotion_crowds", '"人群ID"', '"人群名称"', where,
            scene_expr='"推广场景"', parent_id_expr='"推广单元ID"', parent_name_expr='"推广单元名称"',
            subject_id_expr='"主体ID"', subject_name_expr='"主体名称"', group_exprs=('"人群ID"', '"人群名称"', '"推广场景"', '"推广单元ID"', '"推广单元名称"', '"主体ID"', '"主体名称"'),
            has_direct=False,
        )
        keywords = self._promotion_dimension_rows(
            "store_daily_promotion_bidwords", '"关键词ID"', '"关键词名称"', where,
            scene_expr='"推广场景"', parent_id_expr='"推广单元ID"', parent_name_expr='"推广单元名称"',
            subject_id_expr='"商品ID"', subject_name_expr='"商品名称"', group_exprs=('"关键词ID"', '"关键词名称"', '"推广场景"', '"推广单元ID"', '"推广单元名称"', '"商品ID"', '"商品名称"'),
            has_direct=True,
        )
        items = self._promotion_dimension_rows(
            "store_daily_promotion_items", '"商品ID"', '"商品名称"', where,
            scene_expr='"推广场景"', parent_id_expr='"推广计划ID"', parent_name_expr='"推广计划名称"',
            subject_id_expr='"商品ID"', subject_name_expr='"商品名称"', group_exprs=('"商品ID"', '"商品名称"', '"推广场景"', '"推广计划ID"', '"推广计划名称"'),
            has_direct=True,
        )
        contents = self._promotion_dimension_rows(
            "store_daily_promotion_contents", '"内容ID"', '"内容名称"', where,
            scene_expr='"推广场景"', parent_id_expr='"推广计划ID"', parent_name_expr='"推广计划名称"',
            subject_id_expr='"内容ID"', subject_name_expr='"内容名称"', group_exprs=('"内容ID"', '"内容名称"', '"推广场景"', '"推广计划ID"', '"推广计划名称"'),
            has_direct=False, has_buyers=False, has_new=False, has_member=False,
        )
        coverage = [self._promotion_layer_coverage(key, label, table, entity, start_date, end_date) for key, label, table, entity in (
            ("campaigns", "推广计划", "store_daily_promotion_campaigns", "推广计划ID"),
            ("adgroups", "推广单元", "store_daily_promotion_adgroups", "推广单元ID"),
            ("audiences", "推广人群", "store_daily_promotion_crowds", "人群ID"),
            ("keywords", "推广关键词", "store_daily_promotion_bidwords", "关键词ID"),
            ("items", "推广商品", "store_daily_promotion_items", "商品ID"),
            ("contents", "推广内容", "store_daily_promotion_contents", "内容ID"),
        )]
        return PromotionWorkbenchResponse(
            range_start=start_date, range_end=end_date, summary=summary,
            daily_metrics=daily,
            scenes=scenes, campaigns=campaigns, adgroups=adgroups, audiences=audiences, keywords=keywords, items=items, contents=contents, coverage=coverage,
        )

    @staticmethod
    def _promotion_summary(row: dict[str, object]) -> PromotionSummaryMetric:
        impressions = _integer(row.get("impressions")); clicks = _integer(row.get("clicks")); spend = _decimal(row.get("spend")); paid = _decimal(row.get("paid_amount")); buyers = _integer(row.get("buyers")); new_buyers = _integer(row.get("new_buyers"))
        return PromotionSummaryMetric(campaign_count=_integer(row.get("campaign_count")), impressions=impressions, clicks=clicks, spend=spend, paid_amount=paid, direct_paid_amount=_decimal(row.get("direct_paid_amount")), indirect_paid_amount=_decimal(row.get("indirect_paid_amount")), orders=_integer(row.get("orders")), buyers=buyers, carts=_integer(row.get("carts")), favorites=_integer(row.get("favorites")), new_buyers=new_buyers, member_paid_amount=_decimal(row.get("member_paid_amount")), roi=paid / spend if spend else Decimal("0"), click_rate=Decimal(clicks) / Decimal(impressions) * Decimal("100") if impressions else Decimal("0"), average_click_cost=spend / Decimal(clicks) if clicks else Decimal("0"), click_conversion_rate=Decimal(buyers) / Decimal(clicks) * Decimal("100") if clicks else Decimal("0"), buyer_acquisition_cost=spend / Decimal(buyers) if buyers else Decimal("0"), new_buyer_share=Decimal(new_buyers) / Decimal(buyers) * Decimal("100") if buyers else Decimal("0"))

    def _promotion_dimension_rows(self, table: str, id_expr: str, name_expr: str, where: tuple[object, ...], *, scene_expr: str = "''", parent_id_expr: str = "''", parent_name_expr: str = "''", subject_id_expr: str = "''", subject_name_expr: str = "''", group_exprs: tuple[str, ...], has_direct: bool = True, has_buyers: bool = True, has_new: bool = True, has_member: bool = True) -> list[PromotionDimensionMetric]:
        direct = '"直接成交金额"' if has_direct else "'0'"; indirect = '"间接成交金额"' if has_direct else "'0'"; buyers = '"成交人数"' if has_buyers else "'0'"; new = '"成交新客数"' if has_new else "'0'"; member = '"会员成交金额"' if has_member else "'0'"; natural = '"自然流量转化金额"' if table == "store_daily_promotion_items" else "'0'"
        dimensions = ", ".join(f"{expr} as d{index}" for index, expr in enumerate((id_expr, name_expr, scene_expr, parent_id_expr, parent_name_expr, subject_id_expr, subject_name_expr)))
        groups = ", ".join(group_exprs)
        rows = self._rows(f'''select {dimensions}, sum(cast(coalesce("展现量", '0') as real)) impressions, sum(cast(coalesce("点击量", '0') as real)) clicks, sum(cast(coalesce("花费", '0') as real)) spend, sum(cast(coalesce("总成交金额", '0') as real)) paid_amount, sum(cast(coalesce({direct}, '0') as real)) direct_paid_amount, sum(cast(coalesce({indirect}, '0') as real)) indirect_paid_amount, sum(cast(coalesce("总成交笔数", '0') as real)) orders, sum(cast(coalesce({buyers}, '0') as real)) buyers, sum(cast(coalesce("总购物车数", '0') as real)) carts, sum(cast(coalesce("总收藏数", '0') as real)) favorites, sum(cast(coalesce({new}, '0') as real)) new_buyers, sum(cast(coalesce({member}, '0') as real)) member_paid_amount, sum(cast(coalesce({natural}, '0') as real)) natural_paid_amount from {table} where "店铺ID" = ? and "业务日期" between ? and ? group by {groups} having spend > 0 order by spend desc''', *where)
        return [PromotionDimensionMetric(dimension_id=str(row["d0"] or ""), dimension_name=str(row["d1"] or "未命名"), scene_name=str(row["d2"] or "未分类"), parent_id=str(row["d3"] or ""), parent_name=str(row["d4"] or ""), subject_id=str(row["d5"] or ""), subject_name=str(row["d6"] or ""), impressions=_integer(row["impressions"]), clicks=_integer(row["clicks"]), spend=_decimal(row["spend"]), paid_amount=_decimal(row["paid_amount"]), direct_paid_amount=_decimal(row["direct_paid_amount"]), indirect_paid_amount=_decimal(row["indirect_paid_amount"]), orders=_integer(row["orders"]), buyers=_integer(row["buyers"]), carts=_integer(row["carts"]), favorites=_integer(row["favorites"]), new_buyers=_integer(row["new_buyers"]), member_paid_amount=_decimal(row["member_paid_amount"]), natural_paid_amount=_decimal(row["natural_paid_amount"])) for row in rows]

    def _promotion_layer_coverage(self, key: str, label: str, table: str, entity: str, start_date: date, end_date: date) -> PromotionLayerCoverage:
        rows = self._rows(f'''select count(*) rows, count(distinct "业务日期") covered_days, count(distinct "{entity}") entity_count from {table} where "店铺ID" = ? and "业务日期" between ? and ?''', self._store_id, start_date.isoformat(), end_date.isoformat())
        row = rows[0] if rows else {}
        return PromotionLayerCoverage(key=key, label=label, covered_days=_integer(row.get("covered_days")), row_count=_integer(row.get("rows")), entity_count=_integer(row.get("entity_count")))

    def get_freshness(self) -> list[DataFreshness]:
        datasets = self._dataset_tables()
        freshness: list[DataFreshness] = []
        for label, table in datasets:
            rows = self._rows(
                f'''select min("业务日期") as first_date, max("业务日期") as latest_date
                    from {table} where "店铺ID" = ?''',
                self._store_id,
            )
            latest = rows[0]["latest_date"] if rows else None
            if latest:
                first = rows[0]["first_date"]
                freshness.append(
                    DataFreshness(
                        dataset=label,
                        latest_date=date.fromisoformat(str(latest)),
                        first_date=date.fromisoformat(str(first)) if first else None,
                    )
                )
        return freshness

    @staticmethod
    def _dataset_tables() -> list[tuple[str, str]]:
        return [
            ("店铺日概览", "store_daily_overviews"),
            ("流量来源", "store_daily_traffic_sources"),
            ("商品排行", "store_daily_product_rankings"),
            ("客户分析", "store_daily_customer_overviews"),
            ("会员分析", "store_daily_member_analysis_overviews"),
            ("会员渠道", "store_daily_member_channels"),
            ("客服概览", "store_daily_customer_service_overviews"),
            ("直播概览", "store_daily_live_overviews"),
            ("品销宝", "store_daily_brand_zone_overviews"),
            ("CPS", "store_daily_cps_overviews"),
            ("内容分析", "store_daily_content_overviews"),
            ("U先派样", "store_daily_utry_sample_overviews"),
            ("U先复购", "store_daily_utry_repurchase_overviews"),
            ("推广计划", "store_daily_promotion_campaigns"),
            ("推广人群", "store_daily_promotion_crowds"),
            ("推广单元", "store_daily_promotion_adgroups"),
            ("推广关键词", "store_daily_promotion_bidwords"),
            ("推广商品", "store_daily_promotion_items"),
            ("推广内容", "store_daily_promotion_contents"),
            ("新客礼金", "store_daily_new_customer_discount_overviews"),
            ("购物金", "store_daily_shopping_gold_overviews"),
            ("淘金币", "store_daily_taojinbi_overviews"),
            ("百亿补贴", "store_daily_bybt_overviews"),
            ("百亿补贴商品明细", "store_daily_bybt_items"),
            ("淘宝秒杀", "store_daily_taobao_flash_sale_overviews"),
            ("淘宝秒杀商品明细", "store_daily_taobao_flash_sale_items"),
            ("店播表现", "store_daily_live_store_performance"),
            ("达人直播", "store_daily_live_talent_reports"),
        ]

    def get_flash_sale_analysis(self, start_date: date, end_date: date) -> FlashSaleAnalysisResponse:
        bounds = self._rows(
            '''select min("业务日期") as first_date, max("业务日期") as latest_date
               from store_daily_taobao_flash_sale_overviews where "店铺ID" = ?''',
            self._store_id,
        )
        latest_date = date.fromisoformat(str(bounds[0]["latest_date"])) if bounds and bounds[0]["latest_date"] else None
        selected_rows = self._flash_sale_daily_rows(start_date, end_date)
        period_days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        previous_rows = self._flash_sale_daily_rows(previous_start, previous_end)
        summary = self._flash_sale_summary(selected_rows, start_date, end_date)
        previous_summary = self._flash_sale_summary(previous_rows, previous_start, previous_end)
        by_day = {item.stat_date: item for item in selected_rows}
        daily: list[FlashSaleDailyMetric] = []
        missing_dates: list[date] = []
        empty_dates: list[date] = []
        for offset in range(period_days):
            stat_date = start_date + timedelta(days=offset)
            item = by_day.get(stat_date)
            if item is None:
                missing_dates.append(stat_date)
                daily.append(FlashSaleDailyMetric(stat_date=stat_date, record_status="missing"))
            else:
                if item.record_status == "empty":
                    empty_dates.append(stat_date)
                daily.append(item)
        return FlashSaleAnalysisResponse(
            range_start=start_date,
            range_end=end_date,
            latest_available_date=latest_date,
            summary=summary,
            previous_summary=previous_summary,
            comparison=FlashSaleComparison(
                paid_amount_change_percent=_change_percent(_daily_average(summary.paid_amount, summary.active_days), _daily_average(previous_summary.paid_amount, previous_summary.active_days)),
                paid_order_count_change_percent=_change_percent(_daily_average(summary.paid_order_count, summary.active_days), _daily_average(previous_summary.paid_order_count, previous_summary.active_days)),
                ipv_uv_change_percent=_change_percent(_daily_average(summary.ipv_uv, summary.active_days), _daily_average(previous_summary.ipv_uv, previous_summary.active_days)),
                new_customers_change_percent=_change_percent(_daily_average(summary.new_customers, summary.active_days), _daily_average(previous_summary.new_customers, previous_summary.active_days)),
            ),
            daily_metrics=daily,
            coverage=[item.stat_date for item in selected_rows],
            empty_dates=empty_dates,
            missing_dates=missing_dates,
        )

    def get_promotion_product_item_bounds(self, dataset: str) -> tuple[date, date]:
        table = self._promotion_product_item_table(dataset)
        rows = self._rows(
            f'''select min("业务日期") as first_date, max("业务日期") as latest_date
                from {table} where "店铺ID" = ?''',
            self._store_id,
        )
        first_date = rows[0].get("first_date") if rows else None
        latest_date = rows[0].get("latest_date") if rows else None
        if not first_date or not latest_date:
            label = "百亿补贴" if dataset == "bybt" else "淘宝秒杀"
            raise ValueError(f"{label}商品明细暂无可用数据")
        return date.fromisoformat(str(first_date)), date.fromisoformat(str(latest_date))

    def get_promotion_product_items(
        self,
        dataset: str,
        start_date: date,
        end_date: date,
        *,
        search: str | None,
        page: int,
        page_size: int,
        sort: str,
    ) -> PromotionProductListResponse:
        table = self._promotion_product_item_table(dataset)
        is_bybt = dataset == "bybt"
        activity_id_column = "营销ID" if is_bybt else "活动ID"
        activity_name_expression = "''" if is_bybt else 'coalesce(nullif("活动名称", \'\'), \'\')'
        category_expression = 'coalesce(nullif("百补类目", \'\'), \'\')' if is_bybt else "''"
        status_select = "'' as activity_status" if is_bybt else '''
                coalesce(
                    substr(max(case
                        when nullif("活动状态", '') is not null
                        then "业务日期" || '|' || "活动状态"
                    end), 12),
                    ''
                ) as activity_status'''
        paid_orders_column = "百补支付子订单数" if is_bybt else "活动商品成交笔数"
        paid_items_expression = '"百补支付成交件数"' if is_bybt else "null"
        paid_amount_column = "百补支付金额" if is_bybt else "活动商品成交金额"
        visitors_column = "百补商品访客数" if is_bybt else "活动商品IPVUV"
        new_customers_expression = "null" if is_bybt else '"活动商品引导店铺新客"'
        where, params = self._promotion_product_item_where(start_date, end_date, search)
        group_by = f'"商品ID", "{activity_id_column}"'
        total_row = self._rows(
            f'''select count(*) as total from (
                    select 1 from {table} where {where} group by {group_by}
                )''',
            *params,
        )
        total = _integer(total_row[0].get("total")) if total_row else 0
        order_column = {
            "paid_amount": "paid_amount",
            "paid_order_count": "paid_order_count",
            "visitors": "visitors",
        }.get(sort, "paid_amount")
        offset = (page - 1) * page_size
        rows = self._rows(
            f'''
            select
                "商品ID" as product_id,
                coalesce(max(nullif("商品名称", '')), '') as product_name,
                "{activity_id_column}" as activity_id,
                max({activity_name_expression}) as activity_name,
                max({category_expression}) as category_name,
                {status_select},
                sum(cast(nullif("{visitors_column}", '') as real)) as visitors,
                sum(cast(nullif("{paid_orders_column}", '') as real)) as paid_order_count,
                sum(cast(nullif({paid_items_expression}, '') as real)) as paid_items,
                sum(cast(nullif("{paid_amount_column}", '') as real)) as paid_amount,
                sum(cast(nullif({new_customers_expression}, '') as real)) as new_customers,
                case
                    when sum(cast(nullif("{visitors_column}", '') as real)) > 0
                     and sum(cast(nullif("{paid_orders_column}", '') as real)) is not null
                    then sum(cast(nullif("{paid_orders_column}", '') as real))
                         / sum(cast(nullif("{visitors_column}", '') as real)) * 100
                    else null
                end as conversion_rate,
                count(distinct "业务日期") as active_days
            from {table}
            where {where}
            group by {group_by}
            order by {order_column} desc nulls last, product_id asc
            limit ? offset ?
            ''',
            *params,
            page_size,
            offset,
        )
        return PromotionProductListResponse(
            range_start=start_date,
            range_end=end_date,
            available_start=start_date,
            available_end=end_date,
            total=total,
            page=page,
            page_size=page_size,
            items=[
                PromotionProductMetric(
                    product_id=str(row["product_id"] or ""),
                    product_name=str(row["product_name"] or ""),
                    activity_id=str(row["activity_id"] or ""),
                    activity_name=str(row["activity_name"] or ""),
                    category_name=str(row["category_name"] or ""),
                    activity_status=str(row["activity_status"] or ""),
                    visitors=_optional_integer(row["visitors"]),
                    paid_order_count=_optional_integer(row["paid_order_count"]),
                    paid_items=_optional_integer(row["paid_items"]),
                    paid_amount=_optional_decimal(row["paid_amount"]),
                    new_customers=_optional_integer(row["new_customers"]),
                    conversion_rate=_optional_decimal(row["conversion_rate"]),
                    active_days=_integer(row["active_days"]),
                )
                for row in rows
            ],
        )

    @staticmethod
    def _promotion_product_item_table(dataset: str) -> str:
        if dataset == "bybt":
            return "store_daily_bybt_items"
        if dataset == "flash_sale":
            return "store_daily_taobao_flash_sale_items"
        raise ValueError("不支持的营销商品数据集")

    def _promotion_product_item_where(
        self,
        start_date: date,
        end_date: date,
        search: str | None,
    ) -> tuple[str, list[object]]:
        clauses = ['"店铺ID" = ?', '"业务日期" between ? and ?']
        params: list[object] = [self._store_id, start_date.isoformat(), end_date.isoformat()]
        if search and search.strip():
            clauses.append('(cast("商品ID" as text) like ? or cast("商品名称" as text) like ?)')
            term = f"%{search.strip()}%"
            params.extend((term, term))
        return " and ".join(clauses), params

    def _flash_sale_daily_rows(self, start_date: date, end_date: date) -> list[FlashSaleDailyMetric]:
        rows = self._rows(
            '''select "业务日期" as business_day,
                "活动中商品量级" as item_count, "活动商品IPV" as ipv,
                "活动商品IPVUV" as ipv_uv, "活动商品成交笔数" as paid_order_count,
                "活动商品成交金额" as paid_amount, "活动商品引导店铺新客" as new_customers,
                "活动商品最高爆发系数" as burst_coefficient
               from store_daily_taobao_flash_sale_overviews
               where "店铺ID" = ? and "业务日期" between ? and ? order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        result: list[FlashSaleDailyMetric] = []
        for row in rows:
            values = tuple(row[key] for key in ("item_count", "ipv", "ipv_uv", "paid_order_count", "paid_amount", "new_customers", "burst_coefficient"))
            complete = any(value is not None and value != "" for value in values)
            result.append(FlashSaleDailyMetric(
                stat_date=date.fromisoformat(str(row["business_day"])),
                item_count=_optional_integer(row["item_count"]),
                ipv=_optional_integer(row["ipv"]),
                ipv_uv=_optional_integer(row["ipv_uv"]),
                paid_order_count=_optional_integer(row["paid_order_count"]),
                paid_amount=_optional_decimal(row["paid_amount"]),
                new_customers=_optional_integer(row["new_customers"]),
                burst_coefficient=_optional_decimal(row["burst_coefficient"]),
                record_status="complete" if complete else "empty",
            ))
        return result

    def _flash_sale_summary(self, rows: list[FlashSaleDailyMetric], start_date: date, end_date: date) -> FlashSaleSummary:
        active = [item for item in rows if item.record_status == "complete"]
        paid_amount = sum((item.paid_amount or Decimal("0") for item in active), Decimal("0"))
        paid_order_count = sum((item.paid_order_count or 0 for item in active), 0)
        ipv_uv = sum((item.ipv_uv or 0 for item in active), 0)
        shop_rows = self._rows(
            '''select sum(cast(coalesce("支付金额", '0') as real)) as paid_amount
               from store_daily_overviews where "店铺ID" = ? and "业务日期" between ? and ?''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        shop_paid_amount = _optional_decimal(shop_rows[0]["paid_amount"]) if shop_rows and shop_rows[0]["paid_amount"] is not None else None
        return FlashSaleSummary(
            active_days=len(active),
            item_count_peak=max((item.item_count or 0 for item in active), default=None),
            ipv=sum((item.ipv or 0 for item in active), 0),
            ipv_uv=ipv_uv,
            paid_order_count=paid_order_count,
            paid_amount=paid_amount,
            new_customers=sum((item.new_customers or 0 for item in active), 0),
            burst_coefficient_peak=max((item.burst_coefficient or Decimal("0") for item in active), default=None),
            conversion_rate=_percent_ratio(paid_order_count, ipv_uv),
            customer_unit_price=paid_amount / Decimal(paid_order_count) if paid_order_count else Decimal("0"),
            shop_paid_amount=shop_paid_amount,
            shop_paid_share=paid_amount / shop_paid_amount if shop_paid_amount else None,
        )

    def get_analysis_snapshot(self, start_date: date, end_date: date) -> AnalysisSnapshot:
        daily = self.get_daily_metrics(start_date, end_date)
        daily_by_date = {
            metric.stat_date: AnalysisDailyMetric(stat_date=metric.stat_date)
            for metric in daily
        }
        self._add_daily_values(daily_by_date, "store_daily_live_overviews", "直播成交金额", "live_paid_amount", start_date, end_date)
        self._add_daily_values(daily_by_date, "store_daily_member_analysis_overviews", "会员成交金额", "member_paid_amount", start_date, end_date)
        self._add_daily_values(daily_by_date, "store_daily_customer_service_overviews", "客服销售额", "customer_service_sales", start_date, end_date)
        self._add_daily_values(daily_by_date, "store_daily_brand_zone_overviews", "品销宝成交金额", "brand_paid_amount", start_date, end_date)
        self._add_daily_values(daily_by_date, "store_daily_cps_overviews", "CPS付款金额", "cps_paid_amount", start_date, end_date)
        self._add_daily_values(daily_by_date, "store_daily_content_overviews", "种草成交金额", "content_paid_amount", start_date, end_date)

        return AnalysisSnapshot(
            daily_metrics=sorted(daily_by_date.values(), key=lambda item: item.stat_date),
            customer=self._customer_analysis(start_date, end_date),
            member=self._member_analysis(start_date, end_date),
            customer_service=self._customer_service_analysis(start_date, end_date),
            customer_service_daily=self._customer_service_daily(start_date, end_date),
            customer_service_accounts=self._customer_service_accounts(start_date, end_date),
            live=self._live_analysis(start_date, end_date),
            promotion=self._promotion_analysis(start_date, end_date),
            brand_zone=self._brand_zone_analysis(start_date, end_date),
            cps=self._cps_analysis(start_date, end_date),
            content=self._content_analysis(start_date, end_date),
            new_customer_discount=self._new_customer_discount_analysis(start_date, end_date),
            shopping_gold=self._shopping_gold_analysis(start_date, end_date),
            bybt=self._bybt_analysis(start_date, end_date),
        )

    def _add_daily_values(
        self,
        target: dict[date, AnalysisDailyMetric],
        table: str,
        value_column: str,
        output_field: str,
        start_date: date,
        end_date: date,
    ) -> None:
        rows = self._rows(
            f'''select "业务日期" as business_day, sum(cast(coalesce("{value_column}", '0') as real)) as value
                from {table}
                where "店铺ID" = ? and "业务日期" between ? and ?
                group by "业务日期"''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        for row in rows:
            day = date.fromisoformat(str(row["business_day"]))
            target.setdefault(day, AnalysisDailyMetric(stat_date=day))
            setattr(target[day], output_field, _decimal(row["value"]))

    def _latest_row(self, table: str, start_date: date, end_date: date) -> dict[str, object] | None:
        rows = self._rows(
            f'''select * from {table}
                where "店铺ID" = ? and "业务日期" between ? and ?
                order by "业务日期" desc limit 1''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return rows[0] if rows else None

    def _aggregate(self, table: str, columns: tuple[str, ...], start_date: date, end_date: date) -> dict[str, object]:
        expressions = ", ".join(
            f'''sum(cast(coalesce("{column}", '0') as real)) as "{column}"'''
            for column in columns
        )
        rows = self._rows(
            f'''select {expressions} from {table}
                where "店铺ID" = ? and "业务日期" between ? and ?''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return rows[0] if rows else {}

    def _customer_analysis(self, start_date: date, end_date: date) -> CustomerAnalysis:
        latest = self._latest_row("store_daily_customer_overviews", start_date, end_date) or {}
        shop_customer_rows = self._rows(
            '''select "业务日期" as business_day, "店铺客户数" as shop_customers
               from store_daily_customer_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
                 and "店铺客户数" is not null and trim("店铺客户数") <> ''
               order by "业务日期" desc limit 1''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        latest_shop_customer = shop_customer_rows[0] if shop_customer_rows else {}
        row = self._aggregate(
            "store_daily_customer_overviews",
            ("客户新访", "新访成交", "未购客户回访", "回访成交", "已购客户回访", "老客复购"),
            start_date,
            end_date,
        )
        amount_rows = self._rows(
            '''select
                sum(cast(coalesce(o."支付金额", '0') as real) * cast(coalesce(c."新访支付金额占比", '0') as real)) as new_amount,
                sum(cast(coalesce(o."支付金额", '0') as real) * cast(coalesce(c."未购回访支付金额占比", '0') as real)) as no_purchase_amount,
                sum(cast(coalesce(o."支付金额", '0') as real) * cast(coalesce(c."已购回访支付金额占比", '0') as real)) as repeat_amount,
                sum(cast(coalesce(c."客户新访", '0') as real) * cast(coalesce(c."新访会员占比", '0') as real)) as new_member_count,
                sum(cast(coalesce(c."客户新访", '0') as real) * cast(coalesce(c."新访粉丝占比", '0') as real)) as new_fan_count,
                sum(cast(coalesce(c."未购客户回访", '0') as real) * cast(coalesce(c."未购回访会员占比", '0') as real)) as no_purchase_member_count,
                sum(cast(coalesce(c."未购客户回访", '0') as real) * cast(coalesce(c."未购回访粉丝占比", '0') as real)) as no_purchase_fan_count,
                sum(cast(coalesce(c."已购客户回访", '0') as real) * cast(coalesce(c."已购回访会员占比", '0') as real)) as repeat_member_count,
                sum(cast(coalesce(c."已购客户回访", '0') as real) * cast(coalesce(c."已购回访粉丝占比", '0') as real)) as repeat_fan_count
               from store_daily_customer_overviews c
               left join store_daily_overviews o on o."店铺ID" = c."店铺ID" and o."业务日期" = c."业务日期"
               where c."店铺ID" = ? and c."业务日期" between ? and ?''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        amounts = amount_rows[0] if amount_rows else {}
        shop_customers_value = latest_shop_customer.get("shop_customers")
        new_customers = _integer(row.get("客户新访"))
        new_paid = _integer(row.get("新访成交"))
        repeat_customers = _integer(row.get("老客复购"))
        no_purchase_returners = _integer(row.get("未购客户回访"))
        no_purchase_buyers = _integer(row.get("回访成交"))
        repeat_returners = _integer(row.get("已购客户回访"))
        no_purchase_amount = _decimal(amounts.get("no_purchase_amount"))
        segments = [
            CustomerSegmentMetric(
                key="new",
                label="新访",
                reached=new_customers,
                buyers=new_paid,
                conversion_rate=_percent_ratio(new_paid, new_customers),
                paid_amount=_decimal(amounts.get("new_amount")),
                unit_price=(
                    _decimal(amounts.get("new_amount")) / Decimal(new_paid)
                    if new_paid else Decimal("0")
                ),
                member_rate=(
                    _decimal(amounts.get("new_member_count")) / Decimal(new_customers)
                    if new_customers else Decimal("0")
                ),
                fan_rate=(
                    _decimal(amounts.get("new_fan_count")) / Decimal(new_customers)
                    if new_customers else Decimal("0")
                ),
            ),
            CustomerSegmentMetric(
                key="no_purchase",
                label="未购回访",
                reached=no_purchase_returners,
                buyers=no_purchase_buyers,
                conversion_rate=_percent_ratio(no_purchase_buyers, no_purchase_returners),
                paid_amount=no_purchase_amount,
                unit_price=(no_purchase_amount / Decimal(no_purchase_buyers) if no_purchase_buyers else Decimal("0")),
                member_rate=(
                    _decimal(amounts.get("no_purchase_member_count")) / Decimal(no_purchase_returners)
                    if no_purchase_returners else Decimal("0")
                ),
                fan_rate=(
                    _decimal(amounts.get("no_purchase_fan_count")) / Decimal(no_purchase_returners)
                    if no_purchase_returners else Decimal("0")
                ),
            ),
            CustomerSegmentMetric(
                key="repeat",
                label="已购回访",
                reached=repeat_returners,
                buyers=repeat_customers,
                conversion_rate=_percent_ratio(repeat_customers, repeat_returners),
                paid_amount=_decimal(amounts.get("repeat_amount")),
                unit_price=(
                    _decimal(amounts.get("repeat_amount")) / Decimal(repeat_customers)
                    if repeat_customers else Decimal("0")
                ),
                member_rate=(
                    _decimal(amounts.get("repeat_member_count")) / Decimal(repeat_returners)
                    if repeat_returners else Decimal("0")
                ),
                fan_rate=(
                    _decimal(amounts.get("repeat_fan_count")) / Decimal(repeat_returners)
                    if repeat_returners else Decimal("0")
                ),
            ),
        ]
        daily_rows = self._rows(
            '''select c."业务日期" as business_day,
                c."客户新访" as new_visitors, c."新访成交" as new_paid_buyers,
                c."未购客户回访" as no_purchase_returners, c."回访成交" as no_purchase_buyers,
                c."已购客户回访" as repeat_returners, c."老客复购" as repeat_buyers,
                cast(coalesce(o."支付金额", '0') as real) * cast(coalesce(c."新访支付金额占比", '0') as real) as new_paid_amount,
                cast(coalesce(o."支付金额", '0') as real) * cast(coalesce(c."已购回访支付金额占比", '0') as real) as repeat_paid_amount
               from store_daily_customer_overviews c
               left join store_daily_overviews o on o."店铺ID" = c."店铺ID" and o."业务日期" = c."业务日期"
               where c."店铺ID" = ? and c."业务日期" between ? and ?
                 and coalesce(
                   c."客户新访", c."新访成交", c."未购客户回访", c."回访成交",
                   c."已购客户回访", c."老客复购", c."新访支付金额占比", c."已购回访支付金额占比"
                 ) is not null
               order by c."业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        return CustomerAnalysis(
            shop_customers=(
                None
                if shop_customers_value in (None, "")
                else _integer(shop_customers_value)
            ),
            shop_customers_stat_date=(
                date.fromisoformat(str(latest_shop_customer["business_day"]))
                if latest_shop_customer.get("business_day")
                else None
            ),
            new_customers=new_customers,
            new_customer_paid_buyers=new_paid,
            new_customer_paid_amount=_decimal(amounts.get("new_amount")),
            new_customer_conversion_rate=_percent_ratio(new_paid, new_customers),
            repeat_customers=repeat_customers,
            repeat_customer_paid_amount=_decimal(amounts.get("repeat_amount")),
            repeat_rate=_decimal(latest.get("老客复购率")),
            no_purchase_returners=no_purchase_returners,
            no_purchase_buyers=no_purchase_buyers,
            no_purchase_conversion_rate=_percent_ratio(no_purchase_buyers, no_purchase_returners),
            segments=segments,
            daily_metrics=[
                CustomerDailyMetric(
                    stat_date=date.fromisoformat(str(item["business_day"])),
                    new_visitors=_integer(item["new_visitors"]),
                    new_paid_buyers=_integer(item["new_paid_buyers"]),
                    new_paid_amount=_decimal(item["new_paid_amount"]),
                    no_purchase_returners=_integer(item["no_purchase_returners"]),
                    no_purchase_buyers=_integer(item["no_purchase_buyers"]),
                    repeat_returners=_integer(item["repeat_returners"]),
                    repeat_buyers=_integer(item["repeat_buyers"]),
                    repeat_paid_amount=_decimal(item["repeat_paid_amount"]),
                )
                for item in daily_rows
            ],
        )

    def _member_analysis(self, start_date: date, end_date: date) -> MemberAnalysis:
        latest = self._latest_row("store_daily_member_analysis_overviews", start_date, end_date) or {}
        row = self._aggregate(
            "store_daily_member_analysis_overviews",
            ("会员成交人数", "会员成交金额", "复购会员数", "会员复购金额", "新增会员数", "新会员成交人数"),
            start_date,
            end_date,
        )
        paid_members = _integer(row.get("会员成交人数"))
        paid_amount = _decimal(row.get("会员成交金额"))
        new_members = _integer(row.get("新增会员数"))
        new_paid = _integer(row.get("新会员成交人数"))
        daily_rows = self._rows(
            '''select "业务日期" as business_day, "会员成交人数" as paid_members,
                "会员成交金额" as paid_amount, "复购会员数" as repurchase_members,
                "会员复购金额" as repurchase_amount, "新增会员数" as new_members,
                "新会员成交人数" as new_paid_members
               from store_daily_member_analysis_overviews
               where "店铺ID" = ? and "业务日期" between ? and ? order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        channel_rows = self._rows(
            '''select "入会渠道" as channel_name,
                sum(cast(coalesce("新增会员数", '0') as real)) as new_members,
                sum(cast(coalesce("新会员成交人数", '0') as real)) as paid_new_members,
                sum(cast(coalesce("新会员成交金额", '0') as real)) as paid_amount
               from store_daily_member_channels
               where "店铺ID" = ? and "业务日期" between ? and ?
               group by "入会渠道" order by new_members desc limit 10''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        return MemberAnalysis(
            total_members=_integer(latest.get("会员总数")),
            paid_members=paid_members,
            paid_amount=paid_amount,
            unit_price=paid_amount / paid_members if paid_members else Decimal("0"),
            repurchase_rate=_decimal(latest.get("会员复购率")),
            repurchase_members=_integer(row.get("复购会员数")),
            repurchase_amount=_decimal(row.get("会员复购金额")),
            new_members=new_members,
            new_paid_members=new_paid,
            recruit_conversion_rate=_percent_ratio(new_paid, new_members),
            high_frequency_members=_integer(latest.get("高频复购会员")),
            two_order_members=_integer(latest.get("2单复购会员")),
            first_time_members=_integer(latest.get("首购会员")),
            active_non_buyers=_integer(latest.get("活跃未购会员")),
            inactive_members=_integer(latest.get("沉默会员")),
            repurchase_cycle=_decimal(latest.get("复购周期")),
            daily_metrics=[
                MemberDailyMetric(
                    stat_date=date.fromisoformat(str(item["business_day"])),
                    paid_members=_integer(item["paid_members"]),
                    paid_amount=_decimal(item["paid_amount"]),
                    repurchase_members=_integer(item["repurchase_members"]),
                    repurchase_amount=_decimal(item["repurchase_amount"]),
                    new_members=_integer(item["new_members"]),
                    new_paid_members=_integer(item["new_paid_members"]),
                )
                for item in daily_rows
            ],
            channels=[
                MemberChannelMetric(
                    channel_name=str(item["channel_name"] or "未分类渠道"),
                    new_members=_integer(item["new_members"]),
                    paid_new_members=_integer(item["paid_new_members"]),
                    recruit_conversion_rate=_percent_ratio(_integer(item["paid_new_members"]), _integer(item["new_members"])),
                    paid_amount=_decimal(item["paid_amount"]),
                )
                for item in channel_rows
            ],
        )

    def _customer_service_analysis(self, start_date: date, end_date: date) -> CustomerServiceAnalysis:
        row = self._aggregate(
            "store_daily_customer_service_overviews",
            (
                "客服销售额",
                "客服销售人数",
                "咨询人数",
                "接待人数",
                "成功退款金额",
                "净销售额",
            ),
            start_date,
            end_date,
        )
        average = self._aggregate(
            "store_daily_customer_service_overviews",
            ("平均响应时长（秒）", "客户满意率", "客服销售占比"),
            start_date,
            end_date,
        )
        count_rows = self._rows(
            '''select count(*) as rows_count from store_daily_customer_service_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        count = _integer(count_rows[0]["rows_count"]) if count_rows else 0
        sales_amount = _decimal(row.get("客服销售额"))
        sale_users = _integer(row.get("客服销售人数"))
        consult_users = _integer(row.get("咨询人数"))
        reception_users = _integer(row.get("接待人数"))
        return CustomerServiceAnalysis(
            sales_amount=sales_amount,
            sale_users=sale_users,
            consult_users=consult_users,
            reception_users=reception_users,
            reception_rate=_percent_ratio(reception_users, consult_users),
            sales_conversion_rate=_percent_ratio(sale_users, consult_users),
            sales_ratio=_decimal(average.get("客服销售占比")) / count if count else Decimal("0"),
            avg_reply_seconds=_decimal(average.get("平均响应时长（秒）")) / count if count else Decimal("0"),
            satisfaction_rate=_decimal(average.get("客户满意率")) / count if count else Decimal("0"),
            refund_amount=_decimal(row.get("成功退款金额")),
            net_sales_amount=_decimal(row.get("净销售额")),
        )

    def _customer_service_daily(
        self,
        start_date: date,
        end_date: date,
    ) -> list[CustomerServiceDailyMetric]:
        rows = self._rows(
            '''select
                "业务日期" as business_day,
                "客服销售额" as sales_amount,
                "净销售额" as net_sales_amount,
                "客服销售人数" as sale_users,
                "咨询人数" as consult_users,
                "接待人数" as reception_users,
                "客服销售占比" as sales_ratio,
                "平均响应时长（秒）" as avg_reply_seconds,
                "客户满意率" as satisfaction_rate
               from store_daily_customer_service_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               order by "业务日期"''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return [
            CustomerServiceDailyMetric(
                stat_date=date.fromisoformat(str(row["business_day"])),
                sales_amount=_decimal(row["sales_amount"]),
                net_sales_amount=_decimal(row["net_sales_amount"]),
                sale_users=_integer(row["sale_users"]),
                consult_users=_integer(row["consult_users"]),
                reception_users=_integer(row["reception_users"]),
                sales_ratio=_decimal(row["sales_ratio"]),
                avg_reply_seconds=_decimal(row["avg_reply_seconds"]),
                satisfaction_rate=_decimal(row["satisfaction_rate"]),
            )
            for row in rows
        ]

    def _customer_service_accounts(
        self,
        start_date: date,
        end_date: date,
    ) -> list[CustomerServiceAccountMetric]:
        rows = self._rows(
            '''select
                "旺旺昵称" as account_name,
                sum(cast(coalesce("销售额", '0') as real)) as sales_amount,
                sum(cast(coalesce("净销售额", '0') as real)) as net_sales_amount,
                sum(cast(coalesce("销售人数", '0') as real)) as sale_users,
                sum(cast(coalesce("咨询人数", '0') as real)) as consult_users,
                sum(cast(coalesce("有效接待人数", '0') as real)) as reception_users
               from store_daily_customer_service_accounts
               where "店铺ID" = ? and "业务日期" between ? and ?
               group by "旺旺昵称"
               having sum(cast(coalesce("销售额", '0') as real)) > 0
                   or sum(cast(coalesce("咨询人数", '0') as real)) > 0
               order by sales_amount desc, consult_users desc, account_name
               limit 12''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        accounts: list[CustomerServiceAccountMetric] = []
        for row in rows:
            consult_users = _integer(row["consult_users"])
            reception_users = _integer(row["reception_users"])
            sale_users = _integer(row["sale_users"])
            accounts.append(
                CustomerServiceAccountMetric(
                    account_name=str(row["account_name"] or "未命名客服"),
                    sales_amount=_decimal(row["sales_amount"]),
                    net_sales_amount=_decimal(row["net_sales_amount"]),
                    sale_users=sale_users,
                    consult_users=consult_users,
                    reception_users=reception_users,
                    reception_rate=_percent_ratio(reception_users, consult_users),
                    sales_conversion_rate=_percent_ratio(sale_users, consult_users),
                )
            )
        return accounts

    def _live_analysis(self, start_date: date, end_date: date) -> LiveAnalysis:
        overview = self._aggregate("store_daily_live_overviews", ("直播成交金额", "店播成交金额", "直播中成交金额", "播后成交金额", "直播观看独立访客数"), start_date, end_date)
        performance = self._aggregate("store_daily_live_store_performance", ("观看人数", "商品点击人数", "成交人数", "成交金额"), start_date, end_date)
        paid_amount = _decimal(overview.get("直播成交金额"))
        shop_performance_paid_amount = _decimal(performance.get("成交金额"))
        buyers = _integer(performance.get("成交人数"))
        viewers = _integer(performance.get("观看人数")) or _integer(overview.get("直播观看独立访客数"))
        talent_rows = self._rows(
            '''select "合作主播ID" as talent_id, "合作主播名称" as talent_name,
                sum(cast(coalesce("合作场次数", '0') as real)) as sessions,
                sum(cast(coalesce("商品点击人数", '0') as real)) as item_click_users,
                sum(cast(coalesce("商品加购人数", '0') as real)) as add_cart_users,
                sum(cast(coalesce("成交人数", '0') as real)) as buyers,
                sum(cast(coalesce("成交金额", '0') as real)) as paid_amount,
                sum(cast(coalesce("成交件数", '0') as real)) as paid_items,
                sum(cast(coalesce("成交笔数", '0') as real)) as paid_orders
               from store_daily_live_talent_reports
              where "店铺ID" = ? and "业务日期" between ? and ?
              group by "合作主播ID", "合作主播名称"
              order by paid_amount desc''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        talent_metrics = [
            LiveTalentMetric(
                talent_id=str(row["talent_id"] or ""),
                talent_name=str(row["talent_name"] or "未命名主播"),
                sessions=_integer(row["sessions"]),
                item_click_users=_integer(row["item_click_users"]),
                add_cart_users=_integer(row["add_cart_users"]),
                buyers=_integer(row["buyers"]),
                paid_amount=_decimal(row["paid_amount"]),
                paid_items=_integer(row["paid_items"]),
                paid_orders=_integer(row["paid_orders"]),
                single_output=_decimal(row["paid_amount"]) / _decimal(row["sessions"]) if _decimal(row["sessions"]) else Decimal("0"),
                click_deal_rate=_percent_ratio(_integer(row["buyers"]), _integer(row["item_click_users"])),
            )
            for row in talent_rows
        ]
        daily_rows = self._rows(
            '''select o."业务日期" as business_day, o."直播成交金额" as paid_amount,
                o."店播成交金额" as shop_paid_amount, o."直播中成交金额" as live_during_paid_amount,
                o."播后成交金额" as post_paid_amount, p."观看人数" as viewers,
                p."商品点击人数" as item_click_users, p."成交人数" as buyers
               from store_daily_live_overviews o
               left join store_daily_live_store_performance p
                 on p."店铺ID" = o."店铺ID" and p."业务日期" = o."业务日期"
              where o."店铺ID" = ? and o."业务日期" between ? and ?
              order by o."业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        daily_metrics = [
            LiveDailyMetric(
                stat_date=date.fromisoformat(str(row["business_day"])),
                paid_amount=_decimal(row["paid_amount"]),
                shop_paid_amount=_decimal(row["shop_paid_amount"]),
                live_during_paid_amount=_decimal(row["live_during_paid_amount"]),
                post_paid_amount=_decimal(row["post_paid_amount"]),
                viewers=_integer(row["viewers"]),
                item_click_users=_integer(row["item_click_users"]),
                buyers=_integer(row["buyers"]),
                paid_amount_per_buyer=_decimal(row["live_during_paid_amount"]) / _decimal(row["buyers"]) if _integer(row["buyers"]) else Decimal("0"),
                view_click_rate=_percent_ratio(_integer(row["item_click_users"]), _integer(row["viewers"])),
                click_deal_rate=_percent_ratio(_integer(row["buyers"]), _integer(row["item_click_users"])),
            )
            for row in daily_rows
        ]
        return LiveAnalysis(
            paid_amount=paid_amount,
            shop_paid_amount=_decimal(overview.get("店播成交金额")),
            live_during_paid_amount=_decimal(overview.get("直播中成交金额")),
            post_paid_amount=_decimal(overview.get("播后成交金额")),
            talent_paid_amount=sum((item.paid_amount for item in talent_metrics), Decimal("0")),
            talent_count=len(talent_metrics),
            talent_sessions=sum((item.sessions for item in talent_metrics), 0),
            viewers=viewers,
            buyers=buyers,
            item_click_users=_integer(performance.get("商品点击人数")),
            deal_rate=_percent_ratio(buyers, viewers),
            unit_price=shop_performance_paid_amount / buyers if buyers else Decimal("0"),
            daily_metrics=daily_metrics,
            talents=talent_metrics,
        )

    def _promotion_analysis(self, start_date: date, end_date: date) -> PromotionAnalysis:
        rows = self._rows(
            '''select count(distinct "推广计划ID") as campaign_count,
                sum(cast(coalesce("花费", '0') as real)) as spend,
                sum(cast(coalesce("总成交金额", '0') as real)) as paid_amount,
                sum(cast(coalesce("成交人数", '0') as real)) as buyers
               from store_daily_promotion_campaigns
               where "店铺ID" = ? and "业务日期" between ? and ?''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        row = rows[0] if rows else {}
        spend = _decimal(row.get("spend"))
        if spend == 0:
            overview = self._aggregate("store_daily_overviews", ("全站推广花费", "支付金额", "支付买家数"), start_date, end_date)
            spend = _decimal(overview.get("全站推广花费"))
            paid_amount = _decimal(overview.get("支付金额"))
            buyers = _integer(overview.get("支付买家数"))
            campaign_count = 0
        else:
            paid_amount = _decimal(row.get("paid_amount"))
            buyers = _integer(row.get("buyers"))
            campaign_count = _integer(row.get("campaign_count"))
        return PromotionAnalysis(
            campaign_count=campaign_count,
            spend=spend,
            paid_amount=paid_amount,
            buyers=buyers,
            roi=paid_amount / spend if spend else Decimal("0"),
        )

    def _brand_zone_analysis(self, start_date: date, end_date: date) -> BrandZoneAnalysis:
        row = self._aggregate("store_daily_brand_zone_overviews", ("品销宝展现量", "品销宝点击量", "品销宝点击访客数", "品销宝成交金额", "品销宝成交笔数"), start_date, end_date)
        impressions = _integer(row.get("品销宝展现量"))
        clicks = _integer(row.get("品销宝点击量"))
        paid_amount = _decimal(row.get("品销宝成交金额"))
        orders = _integer(row.get("品销宝成交笔数"))
        return BrandZoneAnalysis(
            impressions=impressions,
            clicks=clicks,
            click_rate=_percent_ratio(clicks, impressions),
            click_visitors=_integer(row.get("品销宝点击访客数")),
            paid_amount=paid_amount,
            paid_order_count=orders,
            conversion_rate=_percent_ratio(orders, clicks),
        )

    def _cps_analysis(self, start_date: date, end_date: date) -> CpsAnalysis:
        measures = ("CPS付款金额", "CPS付款笔数", "CPS点击人数", "CPS付款佣金支出", "CPS付款服务费支出", "CPS付款营销服务费支出", "CPS结算金额", "CPS结算笔数", "CPS结算支出费用", "CPS结算营销服务费支出", "CPS预售定金金额", "CPS预估预售整单金额")
        row = self._aggregate("store_daily_cps_overviews", measures, start_date, end_date)
        daily_rows = self._rows(
            '''select "业务日期" as business_day, "CPS点击人数" as click_visitors,
                "CPS付款金额" as paid_amount, "CPS付款笔数" as paid_order_count,
                (cast(coalesce("CPS付款佣金支出", '0') as real) + cast(coalesce("CPS付款服务费支出", '0') as real) + cast(coalesce("CPS付款营销服务费支出", '0') as real)) as payment_expense,
                "CPS结算金额" as settlement_amount, "CPS结算笔数" as settlement_order_count,
                (cast(coalesce("CPS结算支出费用", '0') as real) + cast(coalesce("CPS结算营销服务费支出", '0') as real)) as settlement_expense,
                "CPS预售定金金额" as preorder_deposit_amount, "CPS预估预售整单金额" as preorder_total_amount
               from store_daily_cps_overviews
              where "店铺ID" = ? and "业务日期" between ? and ?
              order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        daily_metrics = [
            CpsDailyMetric(
                stat_date=date.fromisoformat(str(item["business_day"])),
                click_visitors=_integer(item["click_visitors"]),
                paid_amount=_decimal(item["paid_amount"]),
                paid_order_count=_integer(item["paid_order_count"]),
                payment_expense=_decimal(item["payment_expense"]),
                settlement_amount=_decimal(item["settlement_amount"]),
                settlement_order_count=_integer(item["settlement_order_count"]),
                settlement_expense=_decimal(item["settlement_expense"]),
                preorder_deposit_amount=_decimal(item["preorder_deposit_amount"]),
                preorder_total_amount=_decimal(item["preorder_total_amount"]),
            )
            for item in daily_rows
        ]
        paid_amount = _decimal(row.get("CPS付款金额"))
        payment_expense = _decimal(row.get("CPS付款佣金支出")) + _decimal(row.get("CPS付款服务费支出")) + _decimal(row.get("CPS付款营销服务费支出"))
        settlement_amount = _decimal(row.get("CPS结算金额"))
        return CpsAnalysis(
            paid_amount=paid_amount,
            paid_order_count=_integer(row.get("CPS付款笔数")),
            click_visitors=_integer(row.get("CPS点击人数")),
            payment_expense=payment_expense,
            payment_commission_expense=_decimal(row.get("CPS付款佣金支出")),
            payment_service_expense=_decimal(row.get("CPS付款服务费支出")) + _decimal(row.get("CPS付款营销服务费支出")),
            settlement_expense=_decimal(row.get("CPS结算支出费用")) + _decimal(row.get("CPS结算营销服务费支出")),
            settlement_commission_expense=_decimal(row.get("CPS结算支出费用")),
            settlement_service_expense=_decimal(row.get("CPS结算营销服务费支出")),
            settlement_amount=settlement_amount,
            settlement_order_count=_integer(row.get("CPS结算笔数")),
            payment_cost_rate=payment_expense / paid_amount if paid_amount else Decimal("0"),
            settlement_rate=settlement_amount / paid_amount if paid_amount else Decimal("0"),
            preorder_deposit_amount=_decimal(row.get("CPS预售定金金额")),
            preorder_total_amount=_decimal(row.get("CPS预估预售整单金额")),
            daily_metrics=daily_metrics,
        )

    def _content_analysis(self, start_date: date, end_date: date) -> ContentAnalysis:
        row = self._aggregate("store_daily_content_overviews", ("内容查看次数", "内容查看人数", "商品点击人数", "种草成交金额", "种草成交人数", "内容互动次数", "曝光人数", "内容互动人数", "商品加购人数"), start_date, end_date)
        latest = self._latest_row("store_daily_content_overviews", start_date, end_date) or {}
        daily_rows = self._rows(
            '''select "业务日期" as business_day, "内容查看人数" as viewers,
                "内容互动次数" as interaction_count, "商品点击人数" as product_click_users,
                "商品加购人数" as add_cart_users, "种草成交人数" as paid_buyers,
                "种草成交金额" as paid_amount
               from store_daily_content_overviews
               where "店铺ID" = ? and "业务日期" between ? and ? order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        viewers = _integer(row.get("内容查看人数"))
        return ContentAnalysis(
            view_count=_integer(row.get("内容查看次数")),
            viewers=_integer(row.get("内容查看人数")),
            product_click_users=_integer(row.get("商品点击人数")),
            paid_amount=_decimal(row.get("种草成交金额")),
            paid_buyers=_integer(row.get("种草成交人数")),
            interaction_count=_integer(row.get("内容互动次数")),
            exposure_users=_integer(row.get("曝光人数")),
            interaction_users=_integer(row.get("内容互动人数")),
            add_cart_users=_integer(row.get("商品加购人数")),
            interaction_rate=_percent_ratio(_integer(row.get("内容互动人数")), viewers),
            product_click_rate=_percent_ratio(_integer(row.get("商品点击人数")), viewers),
            paid_amount_ratio=_decimal(latest.get("种草成交金额占比全店")),
            daily_metrics=[
                ContentDailyMetric(
                    stat_date=date.fromisoformat(str(item["business_day"])),
                    viewers=_integer(item["viewers"]),
                    interaction_count=_integer(item["interaction_count"]),
                    product_click_users=_integer(item["product_click_users"]),
                    add_cart_users=_integer(item["add_cart_users"]),
                    paid_buyers=_integer(item["paid_buyers"]),
                    paid_amount=_decimal(item["paid_amount"]),
                )
                for item in daily_rows
            ],
        )

    def _new_customer_discount_analysis(self, start_date: date, end_date: date) -> NewCustomerDiscountAnalysis:
        rows = self._rows(
            '''select "业务日期" as business_day, "商品新访客数" as product_new_visitors,
                "新客支付人数" as paid_buyers, "新客支付金额" as paid_amount,
                "新客支付转化率" as conversion_rate, "店铺新客支付人数" as shop_paid_buyers,
                "店铺新客支付金额" as shop_paid_amount
               from store_daily_new_customer_discount_overviews
               where "店铺ID" = ? and "业务日期" between ? and ? order by "业务日期"''',
            self._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        rows_by_day = {date.fromisoformat(str(item["business_day"])): item for item in rows}
        daily: list[NewCustomerDiscountDailyMetric] = []
        for offset in range((end_date - start_date).days + 1):
            stat_date = start_date + timedelta(days=offset)
            item = rows_by_day.get(stat_date)
            if item is None:
                daily.append(NewCustomerDiscountDailyMetric(stat_date=stat_date, record_status="missing"))
                continue
            activity_fields = (
                item["product_new_visitors"],
                item["paid_buyers"],
                item["paid_amount"],
                item["conversion_rate"],
            )
            activity_complete = all(value is not None for value in activity_fields)
            daily.append(
                NewCustomerDiscountDailyMetric(
                    stat_date=stat_date,
                    product_new_visitors=(
                        _optional_integer(item["product_new_visitors"])
                        if activity_complete
                        else None
                    ),
                    paid_buyers=(
                        _optional_integer(item["paid_buyers"])
                        if activity_complete
                        else None
                    ),
                    paid_amount=(
                        _optional_decimal(item["paid_amount"])
                        if activity_complete
                        else None
                    ),
                    conversion_rate=(
                        _optional_decimal(item["conversion_rate"])
                        if activity_complete
                        else None
                    ),
                    shop_paid_buyers=_optional_integer(item["shop_paid_buyers"]),
                    shop_paid_amount=_optional_decimal(item["shop_paid_amount"]),
                    record_status="complete" if activity_complete else "partial",
                )
            )
        complete_daily = [item for item in daily if item.record_status == "complete"]
        product_new_visitors = sum((item.product_new_visitors or 0 for item in complete_daily), 0)
        paid_buyers = sum((item.paid_buyers or 0 for item in complete_daily), 0)
        paid_amount = sum(
            (item.paid_amount or Decimal("0") for item in complete_daily),
            Decimal("0"),
        )
        shop_paid_buyers = sum((item.shop_paid_buyers or 0 for item in complete_daily), 0)
        shop_paid_amount = sum((item.shop_paid_amount or Decimal("0") for item in complete_daily), Decimal("0"))
        return NewCustomerDiscountAnalysis(
            product_new_visitors=product_new_visitors,
            paid_buyers=paid_buyers,
            paid_amount=paid_amount,
            conversion_rate=_percent_ratio(paid_buyers, product_new_visitors),
            shop_paid_buyers=shop_paid_buyers,
            shop_paid_amount=shop_paid_amount,
            buyer_share=Decimal(paid_buyers) / Decimal(shop_paid_buyers) if shop_paid_buyers else Decimal("0"),
            amount_share=paid_amount / shop_paid_amount if shop_paid_amount else Decimal("0"),
            daily_metrics=daily,
        )

    def _shopping_gold_analysis(self, start_date: date, end_date: date) -> ShoppingGoldAnalysis:
        rows = self._rows(
            '''select
                "业务日期" as business_day,
                "充值总金额" as recharge_amount,
                "支付金额" as paid_amount,
                "充值买家数" as recharge_buyers,
                "支付买家数" as paid_buyers,
                "商品访客数" as product_visitors,
                "充值件数" as recharge_items,
                "充值子订单数" as recharge_sub_order_count,
                "充值成功退款金额" as recharge_refund_amount,
                "充值本金金额" as recharge_capital_amount
               from store_daily_shopping_gold_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               order by "业务日期"''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        daily = [
            ShoppingGoldDailyMetric(
                stat_date=date.fromisoformat(str(row["business_day"])),
                recharge_amount=_decimal(row["recharge_amount"]),
                paid_amount=_decimal(row["paid_amount"]),
                recharge_buyers=_integer(row["recharge_buyers"]),
                paid_buyers=_integer(row["paid_buyers"]),
                product_visitors=_integer(row["product_visitors"]),
                recharge_refund_amount=_decimal(row["recharge_refund_amount"]),
            )
            for row in rows
        ]
        recharge_amount = sum((item.recharge_amount for item in daily), Decimal("0"))
        paid_amount = sum((item.paid_amount for item in daily), Decimal("0"))
        recharge_buyers = sum(item.recharge_buyers for item in daily)
        paid_buyers = sum(item.paid_buyers for item in daily)
        product_visitors = sum(item.product_visitors for item in daily)
        recharge_refund_amount = sum((item.recharge_refund_amount for item in daily), Decimal("0"))
        recharge_items = sum(_integer(row["recharge_items"]) for row in rows)
        recharge_sub_order_count = sum(_integer(row["recharge_sub_order_count"]) for row in rows)
        recharge_capital_amount = sum((_decimal(row["recharge_capital_amount"]) for row in rows), Decimal("0"))
        return ShoppingGoldAnalysis(
            recharge_amount=recharge_amount,
            paid_amount=paid_amount,
            recharge_buyers=recharge_buyers,
            paid_buyers=paid_buyers,
            product_visitors=product_visitors,
            recharge_items=recharge_items,
            recharge_sub_order_count=recharge_sub_order_count,
            recharge_refund_amount=recharge_refund_amount,
            recharge_capital_amount=recharge_capital_amount,
            average_recharge_amount=recharge_amount / recharge_buyers if recharge_buyers else Decimal("0"),
            customer_unit_price=paid_amount / paid_buyers if paid_buyers else Decimal("0"),
            recharge_rate=_percent_ratio(recharge_buyers, product_visitors),
            paid_amount_ratio=paid_amount / recharge_amount if recharge_amount else Decimal("0"),
            daily_metrics=daily,
        )

    def _bybt_analysis(self, start_date: date, end_date: date) -> BybtAnalysis:
        rows = self._rows(
            '''select
                "业务日期" as business_day,
                "百补访客数" as visitors,
                "百补支付买家数" as paid_buyers,
                "百补在线商品数量" as online_items,
                "百补支付金额" as paid_amount,
                "百补子订单数" as paid_sub_order_count,
                "百补支付成交件数" as paid_items
               from store_daily_bybt_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               order by "业务日期"''',
            self._store_id,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        row_by_day = {date.fromisoformat(str(row["business_day"])): row for row in rows}
        daily: list[BybtDailyMetric] = []
        missing_dates: list[date] = []
        for offset in range((end_date - start_date).days + 1):
            stat_date = start_date + timedelta(days=offset)
            row = row_by_day.get(stat_date)
            complete = row is not None and all(
                row[key] is not None
                for key in ("visitors", "paid_buyers", "paid_amount", "paid_sub_order_count", "paid_items")
            )
            if not complete:
                missing_dates.append(stat_date)
                daily.append(BybtDailyMetric(stat_date=stat_date, record_status="missing"))
                continue
            daily.append(BybtDailyMetric(
                stat_date=stat_date,
                visitors=_integer(row["visitors"]),
                paid_buyers=_integer(row["paid_buyers"]),
                paid_amount=_decimal(row["paid_amount"]),
                online_items=_integer(row["online_items"]),
                paid_sub_order_count=_integer(row["paid_sub_order_count"]),
                paid_items=_integer(row["paid_items"]),
            ))
        complete_daily = [item for item in daily if item.record_status == "complete"]
        visitors = sum(item.visitors or 0 for item in complete_daily)
        paid_buyers = sum(item.paid_buyers or 0 for item in complete_daily)
        paid_amount = sum((item.paid_amount or Decimal("0") for item in complete_daily), Decimal("0"))
        paid_sub_order_count = sum(item.paid_sub_order_count or 0 for item in complete_daily)
        paid_items = sum(item.paid_items or 0 for item in complete_daily)
        latest_with_items = next((item for item in reversed(daily) if item.online_items), None)
        return BybtAnalysis(
            visitors=visitors,
            paid_buyers=paid_buyers,
            paid_amount=paid_amount,
            online_items=latest_with_items.online_items if latest_with_items else 0,
            paid_sub_order_count=paid_sub_order_count,
            paid_items=paid_items,
            conversion_rate=_percent_ratio(paid_buyers, visitors),
            customer_unit_price=paid_amount / paid_buyers if paid_buyers else Decimal("0"),
            items_per_buyer=Decimal(paid_items) / Decimal(paid_buyers) if paid_buyers else Decimal("0"),
            expected_days=(end_date - start_date).days + 1,
            covered_days=len(complete_daily),
            missing_dates=missing_dates,
            daily_metrics=daily,
        )

    def _resolve_store_id(self) -> int:
        stores = self._warehouse.list_stores()
        if not stores:
            raise WarehouseDataNotAvailable("No local store has been ingested.")
        return stores[0].store_id

    def _rows(self, statement: str, *params: object) -> list[dict[str, object]]:
        with self._warehouse._connect() as connection:
            return [dict(row) for row in connection.execute(statement, params).fetchall()]

    def _traffic_source_freshness(self) -> list[DataFreshness]:
        rows = self._rows(
            """
            select max("业务日期") as latest_date
            from store_daily_traffic_sources
            where "店铺ID" = ?
            """,
            self._store_id,
        )
        if not rows or not rows[0]["latest_date"]:
            return []
        return [
            DataFreshness(
                dataset="天猫流量来源",
                latest_date=date.fromisoformat(str(rows[0]["latest_date"])),
            )
        ]


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None or value == "" else Decimal(str(value))


def _integer(value: object) -> int:
    return int(_decimal(value))


def _optional_integer(value: object) -> int | None:
    return None if value is None or value == "" else int(Decimal(str(value)))


def _percent_ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else Decimal("0")


def _change_percent(current: Decimal | int, previous: Decimal | int) -> Decimal | None:
    previous_decimal = Decimal(str(previous))
    if previous_decimal == 0:
        return None
    return (Decimal(str(current)) - previous_decimal) / abs(previous_decimal) * Decimal("100")


def _daily_average(value: Decimal | int, days: int) -> Decimal:
    return Decimal(str(value)) / Decimal(days) if days else Decimal("0")
