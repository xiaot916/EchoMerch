import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app.core.local_database import LocalDatabase
from app.integrations.local_warehouse.repository import LocalWarehouseAnalyticsRepository
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_data_coverage_batches_dataset_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "coverage-query-count.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    repository = LocalWarehouseAnalyticsRepository(database_path, store_id=1)
    original = repository._rows
    calls = 0

    def counted(statement: str, *params: object):
        nonlocal calls
        calls += 1
        return original(statement, *params)

    monkeypatch.setattr(repository, "_rows", counted)
    coverage = repository.get_data_coverage(date(2026, 8, 1), date(2026, 8, 7))

    assert len(coverage) == len(repository._dataset_tables())
    assert calls == 2


def test_prefers_campaign_level_promotion_metrics_when_available(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            '''
            insert into store_daily_promotion_campaigns (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "花费", "总成交金额", "成交人数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (1, "2026-08-01", "关键词推广", "42", "核心计划", "12.5", "50", "4"),
        )

    plans = LocalWarehouseAnalyticsRepository(database_path).get_top_promotion_plans(
        date(2026, 8, 1),
        date(2026, 8, 1),
    )

    assert len(plans) == 1
    assert plans[0].plan_name == "核心计划"
    assert plans[0].spend == 12.5
    assert plans[0].paid_amount == 50
    assert plans[0].buyers == 4


def test_counts_successful_empty_campaign_report_as_covered_day(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-empty-day.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    runs = CrawlRunStore(database_path)
    runs.ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    run_id = runs.create_run(
        store_id=1,
        task_type="alimama_campaigns",
        start_day=date(2026, 8, 2),
        end_day=date(2026, 8, 2),
        mode="backfill",
        planned_days=1,
        log_file=tmp_path / "campaign.jsonl",
    )
    runs.record_day(
        run_id=run_id,
        store_id=1,
        business_day=date(2026, 8, 2),
        status="ingested",
        metric_count=0,
    )
    runs.finish_run(
        run_id=run_id,
        status="completed",
        success_days=1,
        skipped_days=0,
        failed_days=0,
    )

    coverage = LocalWarehouseAnalyticsRepository(database_path).get_data_coverage(
        date(2026, 8, 2),
        date(2026, 8, 2),
    )
    campaigns = next(item for item in coverage if item.dataset == "推广计划")

    assert campaigns.status == "complete"
    assert campaigns.covered_days == 1
    assert campaigns.missing_dates == []


def test_physical_campaign_rows_override_an_empty_crawl_marker(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-empty-marker-with-rows.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    runs = CrawlRunStore(database_path)
    runs.ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    run_id = runs.create_run(
        store_id=1,
        task_type="alimama_campaigns",
        start_day=date(2026, 8, 2),
        end_day=date(2026, 8, 2),
        mode="backfill",
        planned_days=1,
        log_file=tmp_path / "campaign.jsonl",
    )
    runs.record_day(
        run_id=run_id,
        store_id=1,
        business_day=date(2026, 8, 2),
        status="ingested",
        metric_count=0,
    )
    runs.finish_run(
        run_id=run_id,
        status="completed",
        success_days=1,
        skipped_days=0,
        failed_days=0,
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            '''
            insert into store_daily_promotion_campaigns (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "花费", "总成交金额", "成交人数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (1, "2026-08-02", "关键词推广", "42", "核心计划", "12.5", "50", "4"),
        )

    coverage = LocalWarehouseAnalyticsRepository(database_path).get_data_coverage(
        date(2026, 8, 2),
        date(2026, 8, 2),
    )
    campaigns = next(item for item in coverage if item.dataset == "推广计划")

    assert campaigns.status == "complete"
    assert campaigns.covered_days == 1
    assert campaigns.no_data_dates == []


def test_groups_campaigns_by_their_real_promotion_scene(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-scenes.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_promotion_campaigns (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "花费", "总成交金额", "成交人数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-01", "关键词推广", "42", "核心计划", "12.5", "50", "4"),
                (1, "2026-08-01", "关键词推广", "43", "扩量计划", "7.5", "30", "2"),
                (1, "2026-08-01", "万相台", "44", "人群计划", "10", "20", "1"),
            ],
        )

    scenes = LocalWarehouseAnalyticsRepository(database_path).get_promotion_scenes(
        date(2026, 8, 1),
        date(2026, 8, 1),
    )

    assert [(scene.scene_name, scene.campaign_count, scene.spend) for scene in scenes] == [
        ("关键词推广", 2, 20),
        ("万相台", 1, 10),
    ]


def test_promotion_daily_metrics_include_dates_without_store_overview(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-daily.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'insert into store_daily_overviews ("店铺ID", "业务日期", "支付金额") values (?, ?, ?)',
            (1, "2026-08-01", "1000"),
        )
        connection.executemany(
            '''
            insert into store_daily_promotion_campaigns (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "花费", "总成交金额", "成交人数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-08-01", "关键词推广", "42", "核心计划", "100", "250", "4"),
                (1, "2026-08-02", "万相台", "43", "补量计划", "50", "100", "2"),
            ],
        )

    repository = LocalWarehouseAnalyticsRepository(database_path)
    store_days = repository.get_daily_metrics(date(2026, 8, 1), date(2026, 8, 2))
    promotion_days = repository.get_promotion_daily_metrics(date(2026, 8, 1), date(2026, 8, 2))

    assert [row.stat_date for row in store_days] == [date(2026, 8, 1)]
    assert [row.stat_date for row in promotion_days] == [date(2026, 8, 1), date(2026, 8, 2)]
    assert sum(row.spend for row in promotion_days) == 150
    assert sum(row.paid_amount for row in promotion_days) == 350


def test_campaign_rename_keeps_one_plan_and_uses_latest_name(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-campaign-rename.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_promotion_campaigns (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "展现量", "点击量", "花费", "总成交金额", "总成交笔数",
                "成交人数", "成交新客数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-09-19", "关键词推广", "42", "旧计划名", "1000", "100", "10", "40", "5", "3", "2"),
                (1, "2026-09-20", "全站推广", "42", "秋季新品计划", "1200", "150", "20", "60", "4", "2", "1"),
            ],
        )

    repository = LocalWarehouseAnalyticsRepository(database_path, store_id=1)
    workbench = repository.get_promotion_workbench(date(2026, 9, 19), date(2026, 9, 20))
    plans = repository.get_top_promotion_plans(date(2026, 9, 19), date(2026, 9, 20))

    assert len(workbench.campaigns) == 1
    assert workbench.campaigns[0].dimension_name == "秋季新品计划"
    assert workbench.campaigns[0].scene_name == "全站推广"
    assert workbench.campaigns[0].spend == 30
    assert workbench.campaigns[0].paid_amount == 100
    assert len(plans) == 1
    assert plans[0].plan_name == "秋季新品计划"
    assert plans[0].spend == 30


def test_buyer_metrics_are_missing_when_orders_exist_but_platform_returns_zero(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-partial-buyer-metrics.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            '''
            insert into store_daily_promotion_campaigns (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "展现量", "点击量", "花费", "总成交金额", "总成交笔数",
                "成交人数", "成交新客数"
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "2026-09-19", "关键词推广", "42", "核心计划", "1000", "100", "30", "90", "5", "4", "2"),
                (1, "2026-09-20", "关键词推广", "42", "核心计划", "2000", "200", "60", "180", "8", "0", "0"),
            ],
        )

    workbench = LocalWarehouseAnalyticsRepository(database_path, store_id=1).get_promotion_workbench(
        date(2026, 9, 19),
        date(2026, 9, 20),
    )

    assert workbench.daily_metrics[1].buyers is None
    assert workbench.daily_metrics[1].new_buyers is None
    assert workbench.summary.buyers == 4
    assert workbench.summary.click_conversion_rate == 4
    assert workbench.summary.buyer_acquisition_cost == 7.5
    assert workbench.campaigns[0].buyer_metric_clicks == 100
    assert workbench.campaigns[0].buyer_metric_spend == 30
    assert workbench.data_quality.status == "partial"
    assert workbench.data_quality.valid_buyer_metric_days == 1
    assert workbench.data_quality.partial_dates == [date(2026, 9, 20)]
    assert "click_conversion_rate" in workbench.data_quality.unavailable_metrics
    assert "推广关键词 0/2 天" in workbench.data_quality.incomplete_layers


def test_adgroup_layer_does_not_invent_unavailable_buyer_metrics(tmp_path: Path) -> None:
    database_path = tmp_path / "promotion-adgroup-without-buyers.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            '''
            insert into store_daily_promotion_campaigns (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "展现量", "点击量", "花费", "总成交金额", "总成交笔数",
                "成交人数", "成交新客数"
            ) values (1, '2026-09-21', '关键词推广', '42', '核心计划',
                      '1000', '100', '30', '90', '5', '4', '2')
            '''
        )
        connection.execute(
            '''
            insert into store_daily_promotion_adgroups (
                "店铺ID", "业务日期", "推广场景", "推广计划ID", "推广计划名称",
                "推广单元ID", "推广单元名称", "商品ID", "商品名称",
                "展现量", "点击量", "花费", "总成交金额", "总成交笔数"
            ) values (1, '2026-09-21', '关键词推广', '42', '核心计划',
                      '7', '核心单元', '1001', '测试商品', '1000', '100', '30', '90', '5')
            '''
        )

    workbench = LocalWarehouseAnalyticsRepository(database_path, store_id=1).get_promotion_workbench(
        date(2026, 9, 21),
        date(2026, 9, 21),
    )

    assert workbench.adgroups[0].buyers is None
    assert workbench.adgroups[0].new_buyers is None
    assert workbench.adgroups[0].buyer_metric_days == 0
