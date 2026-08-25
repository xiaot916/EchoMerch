import sqlite3
from datetime import date
from pathlib import Path

import pytest

from app.core.local_database import LocalDatabase
from app.modules.imports.crawl_run_store import CrawlRunAlreadyRunning, CrawlRunStore


def test_new_database_ledger_foreign_keys_point_to_current_stores(tmp_path: Path) -> None:
    database_path = tmp_path / "ledger.sqlite3"
    LocalDatabase(database_path).initialize_schema()

    with sqlite3.connect(database_path) as conn:
        assert conn.execute('pragma foreign_key_list("crawl_runs")').fetchone()[2] == "stores"
        referenced_tables = {
            row[2]
            for row in conn.execute('pragma foreign_key_list("crawl_run_days")')
        }
        assert referenced_tables == {"stores", "crawl_runs"}


def test_crawl_run_store_round_trips_run_and_day_status(tmp_path: Path) -> None:
    database_path = tmp_path / "ledger.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = CrawlRunStore(database_path)
    store.ensure_store_reference(
        store_id=1,
        store_name="碧芭宝贝旗舰店",
        platform_store_id="2200573698992",
    )

    run_id = store.create_run(
        store_id=1,
        task_type="sycm_overview",
        start_day=date(2026, 8, 1),
        end_day=date(2026, 8, 2),
        mode="backfill",
        planned_days=2,
        log_file=tmp_path / "run.jsonl",
    )
    store.record_day(
        run_id=run_id,
        store_id=1,
        business_day=date(2026, 8, 1),
        status="ingested",
        metric_count=61,
    )
    store.record_day(
        run_id=run_id,
        store_id=1,
        business_day=date(2026, 8, 2),
        status="skipped_existing",
    )
    progress = store.list_runs().runs[0]
    assert progress.success_days == 1
    assert progress.skipped_days == 1
    store.finish_run(
        run_id=run_id,
        status="completed",
        success_days=1,
        skipped_days=1,
        failed_days=0,
    )

    detail = store.get_detail(run_id)
    assert detail.status == "completed"
    assert detail.success_days == 1
    assert [day.status for day in detail.days] == ["ingested", "skipped_existing"]
    assert detail.days[0].metric_count == 61


def test_default_database_connection_is_read_only(tmp_path: Path) -> None:
    database_path = tmp_path / "readonly.sqlite3"
    LocalDatabase(database_path).initialize_schema()

    connection = LocalDatabase(database_path).connect()
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("create table should_not_be_created (id integer)")
    finally:
        connection.close()


def test_no_data_day_counts_as_successful_completion(tmp_path: Path) -> None:
    database_path = tmp_path / "ledger-no-data.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = CrawlRunStore(database_path)
    store.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    run_id = store.create_run(
        store_id=1,
        task_type="taobao_flash_sale_items",
        start_day=date(2026, 8, 18),
        end_day=date(2026, 8, 18),
        mode="backfill",
        planned_days=1,
        log_file=tmp_path / "run.jsonl",
    )
    store.record_day(
        run_id=run_id,
        store_id=1,
        business_day=date(2026, 8, 18),
        status="no_data",
        metric_count=0,
    )
    assert store.get_detail(run_id).success_days == 1


def test_only_one_running_crawl_is_allowed_per_store_and_task(tmp_path: Path) -> None:
    database_path = tmp_path / "ledger.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = CrawlRunStore(database_path)
    store.ensure_store_reference(
        store_id=1,
        store_name="碧芭宝贝旗舰店",
        platform_store_id="2200573698992",
    )
    create_args = {
        "store_id": 1,
        "task_type": "sycm_overview",
        "start_day": date(2026, 8, 1),
        "end_day": date(2026, 8, 1),
        "mode": "daily",
        "planned_days": 1,
        "log_file": tmp_path / "run.jsonl",
    }
    run_id = store.create_run(**create_args)

    with pytest.raises(CrawlRunAlreadyRunning, match=run_id):
        store.create_run(**create_args)


def test_timeout_finalization_preserves_completed_days_and_fails_unrecorded_days(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "timeout-ledger.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    store = CrawlRunStore(database_path)
    store.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    run_id = store.create_run(
        store_id=1,
        task_type="mtop_content_overview",
        start_day=date(2026, 8, 22),
        end_day=date(2026, 8, 23),
        mode="backfill",
        planned_days=2,
        log_file=tmp_path / "run.jsonl",
    )
    store.record_day(
        run_id=run_id,
        store_id=1,
        business_day=date(2026, 8, 22),
        status="ingested",
        metric_count=12,
    )

    cleaned_run_id = store.fail_running_run_for_timeout(
        store_id=1,
        task_type="mtop_content_overview",
        business_day=date(2026, 8, 23),
        error_message="采集子任务超时（60秒），未收到平台响应。",
    )

    assert cleaned_run_id == run_id
    detail = store.get_detail(run_id)
    assert detail.status == "completed_with_errors"
    assert detail.success_days == 1
    assert detail.failed_days == 1
    assert [(item.business_day, item.status) for item in detail.days] == [
        ("2026-08-22", "ingested"),
        ("2026-08-23", "fetch_failed"),
    ]
    assert detail.days[1].error_message == "采集子任务超时（60秒），未收到平台响应。"
    assert store.fail_running_run_for_timeout(
        store_id=1,
        task_type="mtop_content_overview",
        business_day=date(2026, 8, 23),
        error_message="duplicate cleanup",
    ) is None
