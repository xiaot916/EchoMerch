from datetime import date

from app.modules.ai.mcp import CommerceMCPService


def test_generic_promotion_query_exposes_cross_platform_funnel_metrics() -> None:
    result = CommerceMCPService().execute(
        "data.query",
        {
            "store_id": 1,
            "dataset": "promotion_campaigns",
            "dimensions": ["scene"],
            "measures": ["spend", "gmv", "direct_gmv", "roi", "direct_roi", "ctr", "cpc", "click_conversion_rate", "cart_rate", "cart_cost", "buyer_cost"],
            "order_by": ["-roi"],
            "limit": 20,
        },
    )
    assert result.status in {"ok", "partial"}
    assert result.data["rows"]
    assert result.data["aggregates"]["roi"] is not None
    assert result.data["aggregates"]["direct_roi"] is not None
    assert result.data["aggregates"]["ctr"] is not None
    roi_values = [row["roi"] for row in result.data["rows"] if row["roi"] is not None]
    assert roi_values == sorted(roi_values, reverse=True)


def test_generic_period_comparison_supports_dimensions_and_calculated_measures() -> None:
    result = CommerceMCPService().execute(
        "data.compare_periods",
        {
            "store_id": 1,
            "dataset": "promotion_campaigns",
            "dimensions": ["scene"],
            "measures": ["spend", "gmv", "roi", "ctr"],
            "start_date": "2026-08-20",
            "end_date": "2026-08-20",
            "order_by": ["-roi"],
        },
    )
    assert result.status in {"ok", "partial"}
    assert result.data["current"]["rows"]
    assert result.data["previous"]["rows"]
    assert result.data["comparisons"]["roi"]["current"] is not None
    assert next(metric for metric in result.metrics if metric.id == "roi").formula == "gmv / spend"


def test_generic_query_rejects_unregistered_fields() -> None:
    service = CommerceMCPService()
    try:
        service.execute(
            "data.query",
            {"store_id": 1, "dataset": "promotion_campaigns", "dimensions": ["scene; drop table x"], "measures": ["spend"]},
        )
    except ValueError as exc:
        assert "Unknown dimension" in str(exc)
    else:
        raise AssertionError("unregistered dimension was accepted")


def test_generic_data_catalog_exposes_read_only_inventory_datasets() -> None:
    service = CommerceMCPService()
    catalog = service.execute("data.catalog", {"store_id": 1})
    keys = {item["key"] for item in catalog.data["datasets"]}
    assert {"inventory_catalog", "inventory_snapshots"}.issubset(keys)

    result = service.execute(
        "data.query",
        {
            "store_id": 1,
            "dataset": "inventory_catalog",
            "dimensions": ["series", "specification"],
            "measures": ["sku_count"],
            "filters": {"is_active": 1},
            "limit": 20,
        },
    )
    assert result.status == "ok"
    assert result.data["rows"]
    assert result.data["aggregates"]["sku_count"] >= 1


def test_generic_data_catalog_exposes_page_business_datasets() -> None:
    catalog = CommerceMCPService().execute("data.catalog", {"store_id": 1})
    keys = {item["key"] for item in catalog.data["datasets"]}
    assert {
        "promotion_contents", "new_customer_discount", "shopping_gold", "taojinbi",
        "taobao_flash_sale_overviews", "taobao_flash_sale_items",
        "store_activity_calendar_events", "live_store_performance", "live_talent_reports", "bybt_items",
    }.issubset(keys)


def test_generic_data_query_can_filter_inventory_snapshot_as_a_point_in_time_table() -> None:
    result = CommerceMCPService().execute(
        "data.query",
        {
            "store_id": 1,
            "dataset": "inventory_snapshots",
            "dimensions": ["goods_no"],
            "measures": ["available_quantity"],
            "filters": {"business_day": "2026-08-22", "available_quantity": {"lte": 0}},
            "limit": 10,
        },
    )
    assert result.status in {"ok", "no_data"}


def test_generic_data_query_measure_filter_without_dimension_is_valid() -> None:
    """A metric-only query uses an aggregate HAVING, not an invalid bare HAVING."""
    result = CommerceMCPService().execute(
        "data.query",
        {
            "store_id": 1,
            "dataset": "inventory_snapshots",
            "measures": ["available_quantity"],
            "filters": {"business_day": "2026-08-22", "available_quantity": {"lte": 0}},
            "limit": 10,
        },
    )
    assert result.status in {"ok", "no_data"}
    assert "available_quantity" in result.data["aggregates"]


def test_generic_data_query_aggregate_matches_filtered_groups() -> None:
    result = CommerceMCPService().execute(
        "data.query",
        {
            "store_id": 1,
            "dataset": "inventory_catalog",
            "dimensions": ["series"],
            "measures": ["sku_count"],
            "filters": {"is_active": 1, "sku_count": {"gte": 2}},
            "limit": 1000,
        },
    )
    assert result.status == "ok"
    row_total = sum(float(row["sku_count"] or 0) for row in result.data["rows"])
    assert result.data["aggregates"]["sku_count"] == row_total


def test_product_search_supports_series_and_positioning_and_series_profile() -> None:
    service = CommerceMCPService()
    search = service.execute(
        "products.search",
        {"store_id": 1, "query": "大鱼海棠", "series": "大鱼海棠", "positioning": "正装", "limit": 100},
    )
    assert search.status == "ok"
    assert search.data["rows"]
    assert all(row["series"] == "大鱼海棠" for row in search.data["rows"])

    profile = service.execute(
        "products.get_series_profile",
        {"store_id": 1, "series": "大鱼海棠", "positioning": "正装", "start_date": "2026-08-15", "end_date": "2026-08-21"},
    )
    assert profile.status in {"ok", "partial"}
    assert profile.data["product_count"] >= 1
    assert profile.data["sales"]["paid_amount"] is not None


def test_series_profile_does_not_treat_any_rows_as_full_coverage(monkeypatch) -> None:
    class SparseSource:
        _store_id = 1

        @staticmethod
        def get_date_bounds():
            return date(2026, 8, 20), date(2026, 8, 21)

        @staticmethod
        def _rows(statement, *params):
            if "from store_product_catalog" in statement:
                return [{
                    "product_id": "P-1",
                    "product_name": "大鱼海棠正装",
                    "product_type": "正装",
                    "attributes": "",
                    "series": "大鱼海棠",
                    "positioning": "正装",
                }]
            if 'count(distinct "业务日期") as covered_days' in statement:
                return [{"covered_days": 1}]
            if 'select distinct "业务日期" as business_day' in statement:
                return [{"business_day": "2026-08-20"}]
            if "from store_daily_product_rankings" in statement:
                return [{
                    "product_id": "P-1",
                    "row_count": 1,
                    "paid_amount": 100,
                    "refund_amount": 0,
                    "buyers": 5,
                    "visitors": 100,
                    "promotion_spend": 10,
                }]
            raise AssertionError(statement)

    service = CommerceMCPService()
    monkeypatch.setattr(service.analytics, "_source_for_store", lambda _store_id: SparseSource())
    result = service.execute(
        "products.get_series_profile",
        {
            "store_id": 1,
            "series": "大鱼海棠",
            "positioning": "正装",
            "start_date": "2026-08-20",
            "end_date": "2026-08-21",
        },
    )
    assert result.status == "partial"
    assert result.coverage.expected_days == 2
    assert result.coverage.covered_days == 1
    assert result.coverage.missing_dates == ["2026-08-21"]
