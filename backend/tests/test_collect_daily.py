import json
import subprocess
from datetime import date

from scripts import collect_daily


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
