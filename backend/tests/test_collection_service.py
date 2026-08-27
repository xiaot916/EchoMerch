from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes import collection as collection_routes
from app.core.config import settings
from app.integrations import collection_browser
from app.core.local_database import LocalDatabase
from app.main import create_app
from app.modules.access.service import AccessControlStore
from app.modules.collection.registry import COLLECTION_DATASET_BY_KEY, COLLECTION_DATASET_KEYS
from app.modules.collection.schemas import (
    CollectionBatch,
    CollectionOverview,
    DatasetCoverage,
    DatasetTableCoverage,
)
from app.modules.imports.crawl_run_store import CrawlRunStore
from app.modules.collection.service import (
    CollectionBatchConflict,
    CollectionService,
)


def _batch(batch_id: str = "batch_test") -> CollectionBatch:
    return CollectionBatch(
        batch_id=batch_id,
        business_day="2026-08-20",
        dataset_names=["sycm_overviews"],
        trigger="schedule",
        session_source="drissionpage",
        status="running",
        process_id=123,
        started_at="2026-08-21T07:30:00+08:00",
        log_file="test.log",
    )


def test_collection_browser_launcher_waits_for_debug_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "chrome.exe"
    executable.touch()
    connected = iter((False, True))
    launched: dict[str, object] = {}

    class FakeProcess:
        pid = 4321

        @staticmethod
        def poll() -> None:
            return None

    def fake_popen(command, **kwargs):
        launched["command"] = command
        launched["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(collection_browser, "browser_debug_connected", lambda *_args, **_kwargs: next(connected))
    monkeypatch.setattr(collection_browser.subprocess, "Popen", fake_popen)

    result = collection_browser.launch_collection_browser(
        9222,
        profile_dir=tmp_path / "profile",
        browser_path=executable,
        wait_timeout=1,
    )

    assert result.started is True
    assert result.process_id == 4321
    assert "--remote-debugging-port=9222" in launched["command"]
    assert (tmp_path / "profile").is_dir()


def test_collection_browser_launcher_reuses_existing_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collection_browser, "browser_debug_connected", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        collection_browser.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("existing browser should be reused"),
    )

    result = collection_browser.launch_collection_browser(9222)

    assert result.reused is True
    assert result.started is False


def test_dataset_coverage_distinguishes_complete_partial_and_no_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    dataset = COLLECTION_DATASET_BY_KEY["sycm_member_analysis"]
    day = date(2026, 8, 20)

    def table_state(_conn, table: str, _day: date) -> DatasetTableCoverage:
        return DatasetTableCoverage(
            table=table,
            present=table.endswith("overviews"),
            row_count=1 if table.endswith("overviews") else 0,
            latest_date=day.isoformat() if table.endswith("overviews") else None,
        )

    monkeypatch.setattr(service, "_table_coverage", table_state)
    monkeypatch.setattr(service, "_latest_task_attempts", lambda *_args: [])
    partial = service._dataset_coverage(object(), dataset, day)
    assert partial.status == "partial"
    assert partial.present_tables == 1
    assert partial.expected_tables == 2

    monkeypatch.setattr(
        service,
        "_table_coverage",
        lambda _conn, table, _day: DatasetTableCoverage(table=table, present=True, row_count=3),
    )
    complete = service._dataset_coverage(object(), dataset, day)
    assert complete.status == "complete"

    no_data_dataset = COLLECTION_DATASET_BY_KEY["mtop_content_overviews"]
    monkeypatch.setattr(
        service,
        "_table_coverage",
        lambda _conn, table, _day: DatasetTableCoverage(table=table, present=False),
    )
    monkeypatch.setattr(
        service,
        "_latest_task_attempts",
        lambda *_args: [{"day_status": "no_data", "run_status": "completed", "started_at": "2026-08-21T07:00:00", "error_message": None}],
    )
    no_data = service._dataset_coverage(object(), no_data_dataset, day)
    assert no_data.status == "no_data"


def test_skipped_existing_does_not_hide_an_explicit_no_data_day(tmp_path: Path) -> None:
    database_path = tmp_path / "skipped-existing-coverage.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    runs = CrawlRunStore(database_path)
    runs.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="p-1")
    day = date(2026, 8, 26)
    for status in ("no_data", "skipped_existing"):
        run_id = runs.create_run(
            store_id=1,
            task_type="sycm_bybt_items",
            start_day=day,
            end_day=day,
            mode="backfill",
            planned_days=1,
            log_file=tmp_path / f"{status}.jsonl",
        )
        runs.record_day(run_id=run_id, store_id=1, business_day=day, status=status, metric_count=0)
        runs.finish_run(
            run_id=run_id,
            status="completed",
            success_days=1 if status == "no_data" else 0,
            skipped_days=1 if status == "skipped_existing" else 0,
            failed_days=0,
        )
    service = CollectionService(database_path)
    with database.connect() as conn:
        coverage = service._dataset_coverage(
            conn,
            COLLECTION_DATASET_BY_KEY["sycm_bybt_items"],
            day,
        )
    assert coverage.status == "no_data"


def test_bybt_placeholder_overview_is_missing_not_complete(tmp_path: Path) -> None:
    database_path = tmp_path / "bybt-coverage.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with database.connect(initialize=True) as conn:
        conn.execute(
            'insert into store_daily_bybt_overviews ("店铺ID", "业务日期", "百补在线商品数量") values (?, ?, ?)',
            (1, "2026-08-20", "12"),
        )
        conn.commit()
        service = CollectionService(database_path)
        coverage = service._dataset_coverage(conn, COLLECTION_DATASET_BY_KEY["sycm_bybt"], date(2026, 8, 20))
    assert coverage.status == "missing"
    assert coverage.present_tables == 0


def test_new_customer_discount_placeholder_is_partial_not_complete(tmp_path: Path) -> None:
    database_path = tmp_path / "new-customer-coverage.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with database.connect(initialize=True) as conn:
        conn.execute(
            'insert into store_daily_new_customer_discount_overviews ("店铺ID", "业务日期", "店铺新客支付人数", "店铺新客支付金额") values (?, ?, ?, ?)',
            (1, "2026-08-20", "1251", "26684.36"),
        )
        conn.commit()
        service = CollectionService(database_path)
        coverage = service._dataset_coverage(
            conn,
            COLLECTION_DATASET_BY_KEY["sycm_new_customer_discount"],
            date(2026, 8, 20),
        )
    assert coverage.status == "partial"
    assert coverage.present_tables == 0
    assert coverage.tables[0].raw_row_count == 1
    assert coverage.tables[0].status == "partial"
    assert coverage.error_message == "接口已返回店铺级数据，但活动级新客指标为空，尚未形成完整日报。"


def test_complete_dataset_does_not_surface_an_older_task_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    dataset = COLLECTION_DATASET_BY_KEY["databank_daily"]
    day = date(2026, 8, 24)
    monkeypatch.setattr(
        service,
        "_table_coverage_for_dataset",
        lambda _conn, _dataset, table, _day: DatasetTableCoverage(
            table=table, present=True, row_count=1, latest_date=day.isoformat()
        ),
    )
    monkeypatch.setattr(
        service,
        "_latest_task_attempts",
        lambda *_args: [{
            "task_type": "databank_daily",
            "day_status": "ingest_failed",
            "run_status": "completed_with_errors",
            "started_at": "2026-08-24T09:22:00+08:00",
            "error_message": "missing core snapshot data",
        }],
    )

    coverage = service._dataset_coverage(object(), dataset, day)

    assert coverage.status == "complete"
    assert coverage.error_message is None


def test_legacy_bybt_error_is_explained_in_operator_language(
    tmp_path: Path,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")

    assert service._coverage_error_message(
        "The SYCM BYBT overview response is incomplete; required traffic and transaction metrics are missing."
    ) == "百亿补贴接口未返回流量和成交指标（访客、支付买家、支付金额、支付订单、支付件数）；请确认百亿补贴页面权限后重试。"


def test_utry_explicit_empty_subreport_counts_as_covered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    dataset = COLLECTION_DATASET_BY_KEY["utry_overviews"]
    day = date(2026, 8, 23)

    def table_state(_conn, table: str, _day: date) -> DatasetTableCoverage:
        is_sample = table.endswith("sample_overviews")
        return DatasetTableCoverage(
            table=table,
            present=not is_sample,
            row_count=0 if is_sample else 69,
            raw_row_count=0 if is_sample else 69,
            latest_date="2026-08-22" if is_sample else day.isoformat(),
            status="missing" if is_sample else "complete",
        )

    monkeypatch.setattr(service, "_table_coverage", table_state)
    monkeypatch.setattr(
        service,
        "_latest_task_attempts",
        lambda *_args: [{
            "task_type": "utry_overviews",
            "day_status": "ingested",
            "run_status": "completed",
            "started_at": "2026-08-24T09:24:16+08:00",
            "error_message": None,
        }],
    )

    coverage = service._dataset_coverage(object(), dataset, day)

    assert coverage.status == "complete"
    assert coverage.present_tables == 2
    assert coverage.tables[0].status == "no_data"
    assert coverage.tables[0].row_count == 0
    assert coverage.tables[1].status == "complete"


def test_dataset_coverage_uses_preflight_batch_failure_when_no_run_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    dataset = COLLECTION_DATASET_BY_KEY["mtop_content_overviews"]
    day = date(2026, 8, 23)
    database = LocalDatabase(service.database_path)
    database.initialize_schema()
    CrawlRunStore(service.database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    monkeypatch.setattr(
        service,
        "_table_coverage",
        lambda _conn, table, _day: DatasetTableCoverage(table=table, present=False),
    )
    monkeypatch.setattr(service, "_latest_task_attempts", lambda *_args: [])
    monkeypatch.setattr(
        service,
        "_latest_batch_failure",
        lambda *_args: (
            "2026-08-24T10:06:21+08:00",
            "采集标签页未处于对应业务页面。",
        ),
    )
    with database.connect() as conn:
        coverage = service._dataset_coverage(conn, dataset, day)

    assert coverage.status == "failed"
    assert coverage.last_run_status == "failed"
    assert coverage.last_attempt_at == "2026-08-24T10:06:21+08:00"
    assert coverage.error_message == "采集标签页未处于对应业务页面。"


def test_flash_sale_placeholder_is_missing_but_explicit_empty_is_no_data(tmp_path: Path) -> None:
    database_path = tmp_path / "flash-sale-coverage.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="p-1",
    )
    with database.connect(initialize=True) as conn:
        conn.execute(
            '''
            insert into store_daily_taobao_flash_sale_overviews (
                "店铺ID", "业务日期", "活动中商品量级"
            ) values (?, ?, ?)
            ''',
            (1, "2026-08-20", "2"),
        )
        conn.commit()
        service = CollectionService(database_path)
        coverage = service._dataset_coverage(
            conn,
            COLLECTION_DATASET_BY_KEY["taobao_flash_sales"],
            date(2026, 8, 20),
        )
    assert coverage.status == "missing"
    assert coverage.present_tables == 0

    service = CollectionService(database_path)
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            service,
            "_latest_task_attempts",
            lambda *_args: [{
                "day_status": "no_data",
                "run_status": "completed",
                "started_at": "2026-08-21T07:00:00",
                "error_message": None,
            }],
        )
        with database.connect(initialize=True) as conn:
            coverage = service._dataset_coverage(
                conn,
                COLLECTION_DATASET_BY_KEY["taobao_flash_sales"],
                date(2026, 8, 20),
            )
        assert coverage.status == "no_data"
    finally:
        monkeypatch.undo()


def test_running_batch_failure_event_is_visible_before_worker_summary(tmp_path: Path) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    log_file = tmp_path / "batch.log"
    log_file.write_text("[taobao_flash_sale_items] collecting 2026-08-20 ...\n[taobao_flash_sale_items] failed\n", encoding="utf-8")

    assert service._batch_log_failures(str(log_file)) == {
        "taobao_flash_sale_items": "子任务已报告失败，请重试该数据集。",
    }


def test_running_batch_reports_completed_and_current_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    log_file = tmp_path / "batch.log"
    log_file.write_text(
        "[sycm_overviews] collecting 2026-08-20 ...\n"
        "[sycm_overviews] completed\n"
        "[sycm_bybt] collecting 2026-08-20 ...\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        service,
        "_dataset_coverage",
        lambda _conn, dataset, day: DatasetCoverage(
            key=dataset.key, label=dataset.label, group=dataset.group,
            description=dataset.description, status="missing",
            target_day=day.isoformat(), present_tables=0,
            expected_tables=len(dataset.tables), row_count=0,
        ),
    )
    monkeypatch.setattr(service, "_latest_task_attempts", lambda *_args: [])

    progress = service._batch_progress(object(), {
        "dataset_names_json": json.dumps(["sycm_overviews", "sycm_bybt"]),
        "business_day": "2026-08-20",
        "started_at": "2026-08-21T08:00:00+08:00",
        "finished_at": None,
        "log_file": str(log_file),
        "status": "running",
    })

    assert progress["completed_count"] == 1
    assert progress["failed_count"] == 0
    assert progress["settled_count"] == 1
    assert progress["current_dataset_key"] == "sycm_bybt"


def test_multi_worker_dataset_settles_only_after_all_children_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    log_file = tmp_path / "batch.log"
    monkeypatch.setattr(
        service,
        "_dataset_coverage",
        lambda _conn, dataset, day: DatasetCoverage(
            key=dataset.key, label=dataset.label, group=dataset.group,
            description=dataset.description, status="missing",
            target_day=day.isoformat(), present_tables=0,
            expected_tables=len(dataset.tables), row_count=0,
        ),
    )
    monkeypatch.setattr(service, "_latest_task_attempts", lambda *_args: [])
    row = {
        "dataset_names_json": json.dumps(["alimama_promotion_details"]),
        "business_day": "2026-08-20",
        "started_at": "2026-08-21T08:00:00+08:00",
        "finished_at": None,
        "log_file": str(log_file),
        "status": "running",
    }
    log_file.write_text(
        "[alimama_promotion_details:items] completed\n"
        "[alimama_promotion_details:contents] collecting 2026-08-20 ...\n",
        encoding="utf-8",
    )

    partial = service._batch_progress(object(), row)
    assert partial["completed_count"] == 0
    assert partial["settled_count"] == 0

    log_file.write_text(
        "[alimama_promotion_details:items] completed\n"
        "[alimama_promotion_details:contents] completed\n",
        encoding="utf-8",
    )
    complete = service._batch_progress(object(), row)
    assert complete["completed_count"] == 1
    assert complete["settled_count"] == 1


def test_dataset_coverage_does_not_show_error_from_superseded_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    dataset = COLLECTION_DATASET_BY_KEY["mtop_content_overviews"]
    day = date(2026, 8, 20)
    monkeypatch.setattr(
        service,
        "_table_coverage",
        lambda _conn, table, _day: DatasetTableCoverage(
            table=table,
            present=True,
            row_count=3,
            latest_date=day.isoformat(),
        ),
    )
    monkeypatch.setattr(
        service,
        "_latest_task_attempts",
        lambda *_args: [
            {
                "task_type": "mtop_content_overview",
                "day_status": "ingested",
                "run_status": "completed",
                "started_at": "2026-08-22T08:00:00",
                "error_message": None,
            },
            {
                "task_type": "mtop_content_overview",
                "day_status": "fetch_failed",
                "run_status": "completed_with_errors",
                "started_at": "2026-08-22T07:00:00",
                "error_message": "missing _m_h5_tk",
            },
        ],
    )

    coverage = service._dataset_coverage(object(), dataset, day)

    assert coverage.status == "complete"
    assert coverage.last_run_status == "completed"
    assert coverage.error_message is None


def test_operational_snapshot_ingested_run_allows_valid_empty_snapshot_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    dataset = COLLECTION_DATASET_BY_KEY["taobao_operational_snapshots"]
    day = date(2026, 8, 20)

    def table_state(_conn, table: str, _day: date) -> DatasetTableCoverage:
        # Current-price and activity data arrived; the risk-price endpoint
        # legitimately returned an empty collection for this day.
        return DatasetTableCoverage(
            table=table,
            present=not table.endswith("risk_price_items"),
            row_count=4 if not table.endswith("risk_price_items") else 0,
            latest_date=day.isoformat(),
        )

    monkeypatch.setattr(service, "_table_coverage", table_state)
    monkeypatch.setattr(
        service,
        "_latest_task_attempts",
        lambda *_args: [{
            "task_type": "taobao_operational_snapshots",
            "day_status": "ingested",
            "run_status": "completed",
            "started_at": "2026-08-21T07:00:00",
            "error_message": None,
        }],
    )

    coverage = service._dataset_coverage(object(), dataset, day)

    assert coverage.collection_mode == "coverage_snapshot"
    assert coverage.status == "complete"
    assert coverage.row_count == 8


def test_activity_calendar_ingested_run_allows_empty_snapshot_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "collection.sqlite3")
    dataset = COLLECTION_DATASET_BY_KEY["sycm_activity_calendar"]
    day = date(2026, 8, 20)
    monkeypatch.setattr(
        service,
        "_table_coverage",
        lambda _conn, table, _day: DatasetTableCoverage(
            table=table,
            present=False,
            row_count=0,
            latest_date=None,
        ),
    )
    monkeypatch.setattr(
        service,
        "_latest_task_attempts",
        lambda *_args: [{
            "task_type": "sycm_activity_calendar",
            "day_status": "ingested",
            "run_status": "completed",
            "started_at": "2026-08-21T07:00:00",
            "error_message": None,
        }],
    )

    coverage = service._dataset_coverage(object(), dataset, day)

    assert coverage.collection_mode == "coverage_snapshot"
    assert coverage.status == "complete"
    assert coverage.row_count == 0
    assert coverage.present_tables == 1
    assert coverage.tables[0].status == "no_data"


def test_item_details_are_daily_facts_and_only_operational_products_are_snapshots() -> None:
    assert COLLECTION_DATASET_BY_KEY["sycm_bybt_items"].collection_mode == "daily_fact"
    assert COLLECTION_DATASET_BY_KEY["taobao_flash_sale_items"].collection_mode == "daily_fact"
    assert COLLECTION_DATASET_BY_KEY["taobao_operational_snapshots"].collection_mode == "coverage_snapshot"


def test_schedule_resumes_all_enabled_datasets_with_refresh_for_partial_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "schedule.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    service = CollectionService(database_path)
    service.update_schedule(
        enabled=True,
        run_time="07:30",
        dataset_names=["sycm_member_analysis", "sycm_overviews"],
        session_source="drissionpage",
    )
    captured: dict[str, object] = {}

    def fake_overview(*, target_day: date, recent_day_count: int) -> CollectionOverview:
        datasets = [
            DatasetCoverage(
                key="sycm_member_analysis", label="会员分析", group="客户", description="",
                status="partial", target_day=target_day.isoformat(), present_tables=1,
                expected_tables=2, row_count=1,
            ),
            DatasetCoverage(
                key="sycm_overviews", label="店铺经营总览", group="经营", description="",
                status="complete", target_day=target_day.isoformat(), present_tables=1,
                expected_tables=1, row_count=1,
            ),
        ]
        return CollectionOverview(
            target_day=target_day.isoformat(), generated_at="2026-08-21T07:31:00+08:00",
            total_datasets=2, complete_count=1, partial_count=1, missing_count=0,
            failed_count=0, no_data_count=0, collecting_count=0, coverage_percent=50,
            datasets=datasets, recent_days=[], schedule=service.get_schedule(),
        )

    monkeypatch.setattr(service, "overview", fake_overview)
    monkeypatch.setattr(service, "start_batch", lambda **kwargs: captured.update(kwargs) or _batch())
    result = service.trigger_schedule_if_due(
        now=datetime(2026, 8, 21, 7, 31, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert result is not None
    assert captured["dataset_names"] == ["sycm_member_analysis", "sycm_overviews"]
    assert captured["refresh_existing"] is True
    assert captured["resume_from_latest"] is True
    assert service.get_schedule().last_triggered_day == "2026-08-20"

    # The persisted target-day marker prevents duplicate batches on the next
    # scheduler poll, even if the process remains alive.
    assert service.trigger_schedule_if_due(
        now=datetime(2026, 8, 21, 7, 32, tzinfo=ZoneInfo("Asia/Shanghai")),
    ) is None


def test_existing_default_schedule_picks_up_activity_calendar_dataset(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy-schedule.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    legacy_names = [name for name in COLLECTION_DATASET_KEYS if name != "sycm_activity_calendar"]
    with database.connect(initialize=True) as conn:
        conn.execute(
            """
            insert into collection_schedule (
                schedule_id, enabled, run_time, timezone, dataset_names_json,
                session_source, updated_at
            ) values (1, 1, '07:30', 'Asia/Shanghai', ?, 'drissionpage', ?)
            """,
            (json.dumps(legacy_names), "2026-08-24T07:30:00+08:00"),
        )
        conn.commit()

    schedule = CollectionService(database_path).get_schedule()

    assert "sycm_activity_calendar" in schedule.dataset_names


def test_start_batch_rejects_second_running_batch(tmp_path: Path) -> None:
    database_path = tmp_path / "batch-conflict.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    with database.connect(initialize=True) as conn:
        conn.execute(
            """
            insert into collection_batches (
                batch_id, business_day, dataset_names_json, trigger_type,
                session_source, refresh_existing, status, started_at, log_file
            ) values (?, ?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                "batch_existing", "2026-08-20", '["sycm_overviews"]', "manual",
                "drissionpage", 0, "2026-08-21T07:30:00+08:00", "existing.log",
            ),
        )
        conn.commit()

    with pytest.raises(CollectionBatchConflict, match="batch_existing"):
        CollectionService(database_path).start_batch(
            business_day=date(2026, 8, 20),
            dataset_names=["sycm_overviews"],
            session_source="drissionpage",
            refresh_existing=True,
            trigger="manual",
        )


def test_list_batches_recovers_stale_running_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "stale-batch.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    with database.connect(initialize=True) as conn:
        conn.execute(
            """
            insert into collection_batches (
                batch_id, business_day, dataset_names_json, trigger_type,
                session_source, refresh_existing, status, process_id,
                started_at, log_file
            ) values (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                "batch_stale", "2026-08-20", '["sycm_overviews"]', "manual",
                "drissionpage", 0, 4321, "2026-08-21T07:30:00+08:00", "stale.log",
            ),
        )
        conn.commit()

    service = CollectionService(database_path)
    monkeypatch.setattr(service, "_process_exists", lambda _process_id: False)
    monkeypatch.setattr(
        service,
        "_dataset_coverage",
        lambda _conn, dataset, day: DatasetCoverage(
            key=dataset.key,
            label=dataset.label,
            group=dataset.group,
            description=dataset.description,
            status="complete",
            target_day=day.isoformat(),
            present_tables=1,
            expected_tables=1,
            row_count=1,
        ),
    )

    batch = service.list_batches(limit=1)[0]

    assert batch.status == "completed"
    assert batch.completed_count == 1
    assert batch.failed_count == 0
    assert batch.finished_at is not None


def test_start_batch_launches_worker_without_waiting_for_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = CollectionService(tmp_path / "batch.sqlite3")
    launched: dict[str, object] = {}

    class FakeProcess:
        pid = 4321

        @staticmethod
        def wait() -> int:
            return 0

    class ImmediateThread:
        def __init__(self, *, target, args, **_kwargs) -> None:
            self.target = target
            self.args = args

        def start(self) -> None:
            self.target(*self.args)

    def fake_popen(command, **kwargs):
        launched["command"] = command
        launched["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("app.modules.collection.service.subprocess.Popen", fake_popen)
    monkeypatch.setattr("app.modules.collection.service.threading.Thread", ImmediateThread)
    batch = service.start_batch(
        business_day=date(2026, 8, 20),
        dataset_names=["sycm_member_analysis"],
        session_source="drissionpage",
        refresh_existing=True,
        trigger="manual",
    )

    assert "--refresh-existing" in launched["command"]
    assert batch.process_id == 4321
    assert batch.status == "completed_with_errors"


def test_collection_overview_and_schedule_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "collection-api.sqlite3"
    service = CollectionService(database_path)
    AccessControlStore(database_path).ensure_default_admin()
    monkeypatch.setattr(collection_routes, "get_collection_service", lambda: service)

    original_database_path = settings.local_database_path
    original_auth_enabled = settings.auth_enabled
    original_auth_cookie_secure = settings.auth_cookie_secure
    object.__setattr__(settings, "local_database_path", str(database_path))
    object.__setattr__(settings, "auth_enabled", True)
    object.__setattr__(settings, "auth_cookie_secure", False)

    try:
        with TestClient(create_app()) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "123456"},
            )
            assert login.status_code == 200

            overview = client.get("/api/v1/imports/overview", params={"day": "2026-08-20"})
            assert overview.status_code == 200
            assert overview.json()["target_day"] == "2026-08-20"
            assert overview.json()["total_datasets"] > 0
            assert overview.json()["schedule"]["session_source"] == "drissionpage"

            saved = client.post(
                "/api/v1/imports/schedule",
                json={
                    "enabled": True,
                    "run_time": "07:45",
                    "dataset_names": ["sycm_overviews"],
                    "session_source": "drissionpage",
                },
            )
            assert saved.status_code == 200
            assert saved.json()["run_time"] == "07:45"
            assert saved.json()["dataset_names"] == ["sycm_overviews"]

            fetched = client.get("/api/v1/imports/schedule")
            assert fetched.status_code == 200
            assert fetched.json()["enabled"] is True
    finally:
        object.__setattr__(settings, "local_database_path", original_database_path)
        object.__setattr__(settings, "auth_enabled", original_auth_enabled)
        object.__setattr__(settings, "auth_cookie_secure", original_auth_cookie_secure)
