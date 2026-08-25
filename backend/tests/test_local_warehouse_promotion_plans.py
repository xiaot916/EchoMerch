import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.integrations.local_warehouse.repository import LocalWarehouseAnalyticsRepository
from app.modules.imports.crawl_run_store import CrawlRunStore


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
