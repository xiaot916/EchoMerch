import json
import sqlite3
import subprocess
from datetime import date

from scripts import collect_daily
from scripts import collect_sycm_market


def test_plan_defaults_to_yesterday_and_expands_detail_workers(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        collect_daily,
        "yesterday_in_shanghai",
        lambda: date(2026, 8, 20),
    )

    assert collect_daily.main(["--plan", "--datasets", "sycm_overviews,alimama_adgroup_bidwords"]) == 0
    plan = json.loads(capsys.readouterr().out)

    assert plan["business_day"] == "2026-08-20"
    assert plan["timezone"] == "Asia/Shanghai"
    assert len(plan["commands"]) == 3
    assert all("--start 2026-08-20" in command for command in plan["commands"])
    assert all("--end 2026-08-20" in command for command in plan["commands"])
    assert all("SYCM_COOKIE" in command for command in plan["commands"])


def test_dataset_parser_rejects_unknown_names() -> None:
    try:
        collect_daily._parse_dataset_names("sycm_overviews,missing")
    except Exception as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown dataset should be rejected")


def test_member_analysis_daily_plan_includes_channel_section() -> None:
    command = collect_daily.build_child_command(
        collect_daily.DATASET_BY_NAME["sycm_member_analysis"],
        day=date(2026, 8, 20),
        database_path=collect_daily.PROJECT_ROOT / "test.sqlite3",
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=True,
    )

    assert command[command.index("--sections") + 1] == "core,asset,repurchase,acquisition,channel"
    assert "--refresh-existing" in command


def test_operational_snapshots_are_always_refreshed() -> None:
    command = collect_daily.build_child_command(
        collect_daily.DATASET_BY_NAME["taobao_operational_snapshots"],
        day=date(2026, 8, 20),
        database_path=collect_daily.PROJECT_ROOT / "test.sqlite3",
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=False,
    )

    assert "--refresh-existing" in command


def test_activity_calendar_is_always_refreshed() -> None:
    spec = collect_daily.DATASET_BY_NAME["sycm_activity_calendar"]
    assert spec.script == "backfill_sycm_activity_calendar.py"
    command = collect_daily.build_child_command(
        spec,
        day=date(2026, 8, 20),
        database_path=collect_daily.PROJECT_ROOT / "test.sqlite3",
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=False,
    )

    assert "--refresh-existing" in command
    assert command[command.index("--years") + 1] == "2026"


def test_daily_item_details_are_not_forced_into_snapshot_refresh_mode() -> None:
    for name in ("sycm_bybt_items", "taobao_flash_sale_items"):
        command = collect_daily.build_child_command(
            collect_daily.DATASET_BY_NAME[name],
            day=date(2026, 8, 20),
            database_path=collect_daily.PROJECT_ROOT / "test.sqlite3",
            session_source="drissionpage",
            cookie_env="SYCM_COOKIE",
            browser_port=9222,
            refresh_existing=False,
        )

        assert "--refresh-existing" not in command


def test_resume_from_latest_replays_late_arriving_detail_window(tmp_path) -> None:
    database = collect_daily.LocalDatabase(tmp_path / "warehouse.sqlite3")
    database.initialize_schema()
    collect_daily.CrawlRunStore(database.database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="store-1",
    )
    with database.connect(initialize=True) as conn:
        conn.execute(
            '''
            insert into store_daily_bybt_items (
                "店铺ID", "业务日期", "商品ID", "营销ID", "商品名称",
                "百补类目", "经营场景", "销售方式", "赛道类型", "玩法类型"
            ) values (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ("2026-08-22", "1", "1", "商品", "", "", "", "", ""),
        )
        conn.commit()

    spec = collect_daily.DATASET_BY_NAME["sycm_bybt_items"]
    command = collect_daily._commands_for_spec(
        spec,
        day=date(2026, 8, 26),
        database_path=database.database_path,
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=False,
        resume_from_latest=True,
        mutable_refresh_days=4,
    )[0]

    assert command[command.index("--start") + 1] == "2026-08-23"
    assert command[command.index("--end") + 1] == "2026-08-26"
    assert "--refresh-existing" in command


def test_resume_from_latest_replays_a_recent_gap_before_newest_day(tmp_path) -> None:
    database = collect_daily.LocalDatabase(tmp_path / "warehouse-gap.sqlite3")
    database.initialize_schema()
    collect_daily.CrawlRunStore(database.database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="store-1",
    )
    with database.connect(initialize=True) as conn:
        for business_day in (
            "2026-08-20", "2026-08-21", "2026-08-22", "2026-08-23",
            "2026-08-24", "2026-08-26",
        ):
            conn.execute(
                '''
                insert into store_daily_overviews ("店铺ID", "业务日期")
                values (?, ?)
                ''',
                (1, business_day),
            )
        conn.commit()

    spec = collect_daily.DATASET_BY_NAME["sycm_overviews"]
    command = collect_daily._commands_for_spec(
        spec,
        day=date(2026, 8, 26),
        database_path=database.database_path,
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=False,
        resume_from_latest=True,
    )[0]

    assert command[command.index("--start") + 1] == "2026-08-25"
    assert command[command.index("--end") + 1] == "2026-08-26"


def test_resume_from_latest_replays_an_eight_day_gap_before_a_newer_row(tmp_path) -> None:
    database = collect_daily.LocalDatabase(tmp_path / "warehouse-long-gap.sqlite3")
    database.initialize_schema()
    collect_daily.CrawlRunStore(database.database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="store-1",
    )
    with database.connect(initialize=True) as conn:
        for business_day in ("2026-08-30", "2026-09-07"):
            conn.execute(
                'insert into store_daily_overviews ("店铺ID", "业务日期") values (?, ?)',
                (1, business_day),
            )
        conn.commit()

    command = collect_daily._commands_for_spec(
        collect_daily.DATASET_BY_NAME["sycm_overviews"],
        day=date(2026, 9, 7),
        database_path=database.database_path,
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=False,
        resume_from_latest=True,
        coverage_window_days=30,
    )[0]

    assert command[command.index("--start") + 1] == "2026-08-31"
    assert command[command.index("--end") + 1] == "2026-09-07"


def test_resume_from_latest_refreshes_existing_item_ranking_after_qps_limit(tmp_path) -> None:
    database = collect_daily.LocalDatabase(tmp_path / "warehouse-item-qps.sqlite3")
    database.initialize_schema()
    runs = collect_daily.CrawlRunStore(database.database_path)
    runs.ensure_store_reference(store_id=1, store_name="Store 1", platform_store_id="store-1")
    with database.connect(initialize=True) as conn:
        for business_day in ("2026-09-06", "2026-09-07"):
            conn.execute(
                '''insert into store_daily_product_rankings (
                    "店铺ID", "业务日期", "商品ID", "商品名称"
                ) values (?, ?, ?, ?)''',
                (1, business_day, business_day, "商品"),
            )
        conn.commit()
    failed_day = date(2026, 9, 7)
    run_id = runs.create_run(
        store_id=1,
        task_type="sycm_item_rankings",
        start_day=failed_day,
        end_day=failed_day,
        mode="refresh",
        planned_days=1,
        log_file=tmp_path / "item-qps.jsonl",
    )
    runs.record_day(
        run_id=run_id,
        store_id=1,
        business_day=failed_day,
        status="ingest_failed",
        error_message="page 4 fetch failed: HTTP 200, code 1800, message QPS exceeded",
    )
    runs.finish_run(run_id=run_id, status="completed_with_errors", success_days=0, skipped_days=0, failed_days=1)

    command = collect_daily._commands_for_spec(
        collect_daily.DATASET_BY_NAME["sycm_item_rankings"],
        day=failed_day,
        database_path=database.database_path,
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=False,
        resume_from_latest=True,
        coverage_window_days=30,
    )[0]

    assert command[command.index("--start") + 1] == "2026-09-07"
    assert "--refresh-existing" in command


def test_market_gap_plan_uses_one_range_and_skips_completed_days(tmp_path) -> None:
    database = collect_daily.LocalDatabase(tmp_path / "warehouse-market-gap.sqlite3")
    database.initialize_schema()
    with database.connect(initialize=True) as conn:
        collect_sycm_market._schema(conn)
        for table in ("sycm_market_rankings", "sycm_market_keywords"):
            # The test only needs one row per table to establish the initial
            # baseline. The collectors themselves validate full source shape.
            if table == "sycm_market_rankings":
                conn.execute(
                    '''insert into sycm_market_rankings (
                        stat_start, stat_end, date_type, parent_cate_id, cate_id,
                        cate_flag, rank_type, rank_metric, rank_no, entity_type,
                        raw_json, fetched_at
                    ) values (?, ?, 'day', 'p', 'c', '1', 'item', 'gmv', 1, 'item', '{}', 'now')''',
                    ("2026-08-30", "2026-08-30"),
                )
            else:
                conn.execute(
                    '''insert into sycm_market_keywords (
                        stat_start, stat_end, date_type, parent_cate_id, cate_id,
                        cate_flag, keyword_type, rank_metric, rank_no, keyword,
                        raw_json, fetched_at
                    ) values (?, ?, 'day', 'p', 'c', '1', 'search', 'hot', 1, 'word', '{}', 'now')''',
                    ("2026-08-30", "2026-08-30"),
                )
        conn.commit()

    command = collect_daily._commands_for_spec(
        collect_daily.DATASET_BY_NAME["sycm_market"],
        day=date(2026, 9, 2),
        database_path=database.database_path,
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        refresh_existing=False,
        resume_from_latest=True,
        coverage_window_days=30,
    )[0]

    assert command[command.index("--start") + 1] == "2026-08-31"
    assert command[command.index("--end") + 1] == "2026-09-02"
    assert "--skip-existing" in command


def test_market_schema_creates_both_report_tables(tmp_path) -> None:
    database_path = tmp_path / "market-schema.sqlite3"
    with sqlite3.connect(database_path) as conn:
        collect_sycm_market._schema(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }

    assert {"sycm_market_rankings", "sycm_market_keywords"} <= tables


def test_timed_out_child_closes_its_crawl_ledger(monkeypatch, tmp_path) -> None:
    cleanup_calls = []

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=60)

    def record_cleanup(**kwargs):
        cleanup_calls.append(kwargs)
        return "crawl-timeout-run"

    monkeypatch.setattr(collect_daily.subprocess, "run", raise_timeout)
    monkeypatch.setattr(collect_daily, "_cleanup_timed_out_crawl_run", record_cleanup)

    status, summary = collect_daily.run_collection(
        day=date(2026, 8, 23),
        dataset_names=["mtop_content_overviews"],
        database_path=tmp_path / "warehouse.sqlite3",
        session_source="drissionpage",
        cookie_env="SYCM_COOKIE",
        browser_port=9222,
        timeout=60,
    )

    assert status == 1
    assert cleanup_calls == [
        {
            "database_path": tmp_path / "warehouse.sqlite3",
            "label": "mtop_content_overviews",
            "day": date(2026, 8, 23),
            "timeout": 60,
        }
    ]
    assert summary["results"][0]["crawl_run_id"] == "crawl-timeout-run"


def test_plan_exposes_bounded_parallelism(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        collect_daily,
        "yesterday_in_shanghai",
        lambda: date(2026, 8, 20),
    )

    assert collect_daily.main([
        "--plan",
        "--datasets",
        "sycm_overviews,sycm_bybt",
        "--parallelism",
        "3",
    ]) == 0
    plan = json.loads(capsys.readouterr().out)

    assert plan["parallelism"] == 3


def test_parallelism_must_be_positive() -> None:
    try:
        collect_daily.run_collection(
            day=date(2026, 8, 20),
            dataset_names=["sycm_overviews"],
            database_path=collect_daily.PROJECT_ROOT / "test.sqlite3",
            session_source="drissionpage",
            cookie_env="SYCM_COOKIE",
            browser_port=9222,
            parallelism=0,
        )
    except ValueError as exc:
        assert "parallelism" in str(exc)
    else:
        raise AssertionError("parallelism=0 should be rejected")
