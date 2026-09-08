"""Run the persisted daily collectors for one completed business day.

The command intentionally orchestrates the existing, independently-tested
backfill workers instead of duplicating their request and ingestion logic.
With no date argument it targets yesterday in Asia/Shanghai, which is the
first fully completed report day at the time a daily scheduler normally runs.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.business_days import parse_business_day, yesterday_in_shanghai  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.local_database import (  # noqa: E402
    BUSINESS_DAY,
    CRAWL_RUN_ID,
    CRAWL_TASK_TYPE,
    DAY_STATUS,
    STORE_ID,
    LocalDatabase,
    q,
)
from app.modules.collection.coverage import (  # noqa: E402
    DEFAULT_COVERAGE_WINDOW_DAYS,
    DatasetGapAudit,
    audit_dataset_coverage,
)
from app.modules.collection.registry import COLLECTION_DATASET_BY_KEY  # noqa: E402
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    script: str
    description: str
    supports_database: bool = True
    # Browser page/resource group. Jobs in one group must not navigate the
    # same SPA concurrently; None means the dataset is isolated by name.
    platform_group: str | None = None


# Keep this list explicit and ordered.  The order mirrors the warehouse layers
# and makes console output stable for scheduled runs and troubleshooting.
DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec("sycm_overviews", "backfill_sycm_overviews.py", "SYCM 店铺总览", platform_group="sycm"),
    DatasetSpec("sycm_bybt", "backfill_sycm_bybt.py", "SYCM 生意参谋 BYBT", platform_group="sycm"),
    DatasetSpec("sycm_bybt_items", "backfill_sycm_bybt_items.py", "SYCM 百亿补贴商品明细", platform_group="sycm"),
    DatasetSpec("sycm_customer_overviews", "backfill_sycm_customer_overviews.py", "SYCM 客户概览", platform_group="sycm"),
    DatasetSpec("sycm_item_rankings", "backfill_sycm_item_rankings.py", "SYCM 商品排行", platform_group="sycm"),
    DatasetSpec("sycm_live", "backfill_sycm_live.py", "SYCM 直播", platform_group="sycm"),
    DatasetSpec("sycm_member_analysis", "backfill_sycm_member_analysis.py", "SYCM 会员分析", platform_group="sycm"),
    DatasetSpec("sycm_new_customer_discount", "backfill_sycm_new_customer_discount.py", "SYCM 新客优惠", platform_group="sycm"),
    DatasetSpec("sycm_shopping_gold", "backfill_sycm_shopping_gold.py", "SYCM 淘金币", platform_group="sycm"),
    DatasetSpec("sycm_traffic_sources", "backfill_sycm_traffic_sources.py", "SYCM 流量来源", platform_group="sycm"),
    DatasetSpec("sycm_market", "collect_sycm_market.py", "SYCM 市场排行与搜索词", supports_database=False, platform_group="sycm"),
    DatasetSpec("mtop_content_overviews", "backfill_mtop_content_overviews.py", "内容效果总览", platform_group="mtop"),
    DatasetSpec("mtop_taojinbi", "backfill_mtop_taojinbi.py", "淘金币 MTop", platform_group="mtop"),
    DatasetSpec("customer_service", "backfill_customer_service.py", "客服总览与账号", platform_group="customer_service"),
    DatasetSpec("cps_overviews", "backfill_cps_overviews.py", "淘宝客 CPS 总览", platform_group="alimama"),
    DatasetSpec("brandsearch_reports", "backfill_brandsearch_reports.py", "品销宝品牌专区", platform_group="brandsearch"),
    DatasetSpec("taobao_flash_sales", "backfill_taobao_flash_sales.py", "淘宝秒杀", platform_group="taobao"),
    DatasetSpec("taobao_flash_sale_items", "backfill_taobao_flash_sale_items.py", "淘宝秒杀商品明细", platform_group="taobao"),
    DatasetSpec("taobao_operational_snapshots", "backfill_taobao_operational_snapshots.py", "淘宝红线价、当前价格与活动在线快照", platform_group="taobao"),
    DatasetSpec("sycm_activity_calendar", "backfill_sycm_activity_calendar.py", "SYCM 活动日历当前快照", platform_group="sycm"),
    DatasetSpec("utry_overviews", "backfill_utry_overviews.py", "U先派样与复购商品数据", platform_group="utry"),
    DatasetSpec("alimama_campaigns", "backfill_alimama_campaigns.py", "阿里妈妈计划", platform_group="alimama"),
    DatasetSpec("alimama_crowds", "backfill_alimama_crowds.py", "阿里妈妈人群", platform_group="alimama"),
    DatasetSpec("alimama_promotion_details", "backfill_alimama_promotion_details.py", "阿里妈妈推广明细", platform_group="alimama"),
    DatasetSpec("alimama_adgroup_bidwords", "backfill_alimama_adgroup_bidwords.py", "阿里妈妈单元/关键词", platform_group="alimama"),
    DatasetSpec("databank_daily", "backfill_databank_daily.py", "品牌数据银行日报", platform_group="databank"),
)

DATASET_BY_NAME = {item.name: item for item in DATASETS}
DEFAULT_DATASET_NAMES = tuple(item.name for item in DATASETS)

# The worker scripts use stable crawl task types in the coverage ledger.  Keep
# this mapping in the orchestrator so a child terminated on timeout can have
# its already-created ledger closed deterministically.
CRAWL_TASK_TYPES: dict[str, tuple[str, ...]] = {
    "sycm_overviews": ("sycm_overview",),
    "sycm_bybt": ("sycm_bybt",),
    "sycm_bybt_items": ("sycm_bybt_items",),
    "sycm_customer_overviews": ("sycm_customer_overview",),
    "sycm_item_rankings": ("sycm_item_rankings",),
    "sycm_live": ("sycm_live",),
    "sycm_member_analysis": ("sycm_member_analysis",),
    "sycm_new_customer_discount": ("sycm_new_customer_discount",),
    "sycm_shopping_gold": ("sycm_shopping_gold",),
    "sycm_traffic_sources": ("sycm_traffic_source",),
    "mtop_content_overviews": ("mtop_content_overview",),
    "mtop_taojinbi": ("mtop_taojinbi",),
    "customer_service": ("customer_service",),
    "cps_overviews": ("cps_overview",),
    "brandsearch_reports": ("brandsearch_report",),
    "taobao_flash_sales": ("taobao_flash_sale",),
    "taobao_flash_sale_items": ("taobao_flash_sale_items",),
    "taobao_operational_snapshots": ("taobao_operational_snapshots",),
    "sycm_activity_calendar": ("sycm_activity_calendar",),
    "utry_overviews": ("utry_overviews",),
    "alimama_campaigns": ("alimama_campaigns",),
    "alimama_crowds": ("alimama_crowds",),
    "alimama_promotion_details:item": ("alimama_item_promotion",),
    "alimama_promotion_details:content": ("alimama_content_promotion",),
    "alimama_adgroup_bidwords:adgroup": ("alimama_adgroups",),
    "alimama_adgroup_bidwords:bidword": ("alimama_bidwords",),
    "databank_daily": ("databank_daily",),
    "sycm_market": ("sycm_market",),
}
PROMOTION_DATASET_NAMES = frozenset({
    "cps_overviews",
    "brandsearch_reports",
    "alimama_campaigns",
    "alimama_crowds",
    "alimama_promotion_details",
    "alimama_adgroup_bidwords",
})
ALWAYS_REFRESH_DATASET_NAMES = frozenset({
    "taobao_operational_snapshots",
    "sycm_activity_calendar",
})
# These source reports can land after the first daily run.  Replaying their
# short trailing window avoids a transient empty response becoming permanent,
# while the per-worker upsert keeps the retry idempotent.
LATE_ARRIVING_DATASET_NAMES = frozenset({
    "sycm_bybt",
    "sycm_bybt_items",
    "sycm_new_customer_discount",
    "mtop_content_overviews",
    "taobao_flash_sales",
    "taobao_flash_sale_items",
})


def _parse_day_argument(value: str) -> date:
    try:
        return parse_business_day(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid business day {value!r}; use YYYY-MM-DD, today, or yesterday"
        ) from exc


def _parse_dataset_names(value: str) -> list[str]:
    names = [part.strip() for part in value.split(",") if part.strip()]
    if not names or names == ["all"]:
        return list(DEFAULT_DATASET_NAMES)
    unknown = sorted(set(names) - DATASET_BY_NAME.keys())
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown dataset(s): " + ", ".join(unknown) + "; use --list-datasets"
        )
    # Preserve user order while avoiding an accidental duplicate invocation.
    return list(dict.fromkeys(names))


def selected_specs(names: Sequence[str]) -> list[DatasetSpec]:
    return [DATASET_BY_NAME[name] for name in names]


def build_child_command(
    spec: DatasetSpec,
    *,
    day: date,
    start_day: date | None = None,
    database_path: Path,
    session_source: str,
    cookie_env: str,
    browser_port: int,
    refresh_existing: bool,
    promotion_refresh_days: int = 0,
) -> list[str]:
    effective_cookie_env = "DATABANK_COOKIE" if spec.name == "databank_daily" and cookie_env == "SYCM_COOKIE" else cookie_env
    range_start = start_day or day
    range_end = day
    rolling_promotion = spec.name in PROMOTION_DATASET_NAMES and promotion_refresh_days > 1
    if rolling_promotion:
        range_start = day - timedelta(days=promotion_refresh_days - 1)
    command = [
        sys.executable,
        str(Path(__file__).resolve().with_name(spec.script)),
        "--start",
        range_start.isoformat(),
        "--end",
        range_end.isoformat(),
        "--session-source",
        session_source,
        "--cookie-env",
        effective_cookie_env,
        "--browser-port",
        str(browser_port),
    ]
    if spec.name == "sycm_market":
        command = [
            sys.executable,
            str(Path(__file__).resolve().with_name(spec.script)),
            "--start",
            range_start.isoformat(),
            "--end",
            range_end.isoformat(),
            "--date-type",
            "day",
            "--session-source",
            session_source,
            "--cookie-env",
            cookie_env,
            "--browser-port",
            str(browser_port),
            "--database",
            str(database_path),
            "--skip-existing",
            "--continue-on-error",
        ]
        return command
    if spec.supports_database:
        command.extend(["--database-path", str(database_path)])
    if spec.name == "sycm_member_analysis":
        # The worker defaults to overview sections only. Daily completeness
        # also owns the channel table, so request it explicitly.
        command.extend(["--sections", "core,asset,repurchase,acquisition,channel"])
    if spec.name == "sycm_activity_calendar":
        # The endpoint returns an annual calendar. Daily scheduling refreshes
        # only the current business year; prior years stay persisted.
        command.extend(["--years", str(day.year)])
    if refresh_existing or rolling_promotion or spec.name in ALWAYS_REFRESH_DATASET_NAMES:
        command.append("--refresh-existing")
    return command


def _latest_completed_day(
    *,
    spec: DatasetSpec,
    database_path: Path,
    store_id: int = 1,
) -> date | None:
    """Return the newest persisted or explicitly no-data day for one dataset.

    The coverage ledger matters here: an explicit platform ``no_data`` result
    has no table row for detail datasets, but it is still a completed day and
    must not make the scheduler replay the entire history.
    """

    dataset = COLLECTION_DATASET_BY_KEY.get(spec.name)
    if dataset is None or not database_path.exists():
        return None
    database = LocalDatabase(database_path)
    try:
        with database.connect() as conn:
            table_latest_days: list[date] = []
            for table in dataset.tables:
                exists = conn.execute(
                    "select 1 from sqlite_master where type = 'table' and name = ?",
                    (table,),
                ).fetchone()
                if exists is None:
                    continue
                row = conn.execute(
                    f"select max({q(BUSINESS_DAY)}) as latest_day from {q(table)} "
                    f"where {q(STORE_ID)} = ?",
                    (store_id,),
                ).fetchone()
                if row and row["latest_day"]:
                    table_latest_days.append(date.fromisoformat(str(row["latest_day"])))
            candidates: list[date] = []
            ledger_latest: dict[str, date] = {}
            if dataset.task_types:
                placeholders = ",".join("?" for _ in dataset.task_types)
                rows = conn.execute(
                    f"""
                    select r.{q(CRAWL_TASK_TYPE)} as task_type,
                           max(d.{q(BUSINESS_DAY)}) as latest_day
                    from crawl_run_days d
                    inner join crawl_runs r
                      on r.{q(CRAWL_RUN_ID)} = d.{q(CRAWL_RUN_ID)}
                    where d.{q(STORE_ID)} = ?
                      and r.{q(CRAWL_TASK_TYPE)} in ({placeholders})
                      and d.{q(DAY_STATUS)} in ('ingested', 'no_data')
                    group by r.{q(CRAWL_TASK_TYPE)}
                    """,
                    (store_id, *dataset.task_types),
                ).fetchall()
                ledger_latest = {
                    str(row["task_type"]): date.fromisoformat(str(row["latest_day"]))
                    for row in rows
                    if row["latest_day"]
                }
            if len(dataset.tables) == 1 and table_latest_days:
                candidates.append(max(table_latest_days))
            elif table_latest_days:
                # A multi-table dataset is only caught up through its oldest
                # persisted component day. Using the maximum would skip a
                # companion table that is still behind.
                candidates.append(min(table_latest_days))
            if ledger_latest and all(task_type in ledger_latest for task_type in dataset.task_types):
                ledger_day = max(ledger_latest.values()) if len(dataset.tables) == 1 else min(ledger_latest.values())
                candidates.append(ledger_day)
    except Exception:
        # Scheduling a new report day must remain available if an older local
        # database cannot yet expose a coverage table.
        return None
    return max(candidates, default=None)


def _resume_start_day(
    *,
    spec: DatasetSpec,
    day: date,
    database_path: Path,
    mutable_refresh_days: int,
    coverage_window_days: int = DEFAULT_COVERAGE_WINDOW_DAYS,
) -> date:
    latest = _latest_completed_day(spec=spec, database_path=database_path)
    next_after_latest = latest + timedelta(days=1) if latest else day
    # A later successful day does not prove that every earlier day landed.
    # Inspect a short trailing window so a missed day such as yesterday can be
    # replayed even when the database already contains a newer report.
    audit_start = _earliest_uncovered_day(
        spec=spec,
        day=day,
        database_path=database_path,
        window_days=max(coverage_window_days, mutable_refresh_days),
    )
    if audit_start is not None:
        next_after_latest = min(next_after_latest, audit_start)
    if spec.name not in LATE_ARRIVING_DATASET_NAMES or mutable_refresh_days <= 1:
        return min(next_after_latest, day)
    trailing_start = day - timedelta(days=mutable_refresh_days - 1)
    return min(next_after_latest, trailing_start)


def _earliest_uncovered_day(
    *,
    spec: DatasetSpec,
    day: date,
    database_path: Path,
    window_days: int,
) -> date | None:
    """Return the first bounded, observed coverage gap for a dataset."""
    dataset = COLLECTION_DATASET_BY_KEY.get(spec.name)
    if dataset is None or not database_path.exists() or window_days < 1:
        return None
    database = LocalDatabase(database_path)
    try:
        with database.connect() as conn:
            audit = audit_dataset_coverage(
                conn,
                dataset,
                target_day=day,
                window_days=window_days,
            )
            return audit.backfill_start_day
    except Exception:
        return None


def _coverage_audit(
    *,
    spec: DatasetSpec,
    day: date,
    database_path: Path,
    window_days: int,
) -> DatasetGapAudit | None:
    dataset = COLLECTION_DATASET_BY_KEY.get(spec.name)
    if dataset is None or not database_path.exists():
        return None
    try:
        database = LocalDatabase(database_path)
        with database.connect() as conn:
            return audit_dataset_coverage(
                conn,
                dataset,
                target_day=day,
                window_days=window_days,
            )
    except Exception:
        return None


def _commands_for_spec(
    spec: DatasetSpec,
    *,
    day: date,
    database_path: Path,
    session_source: str,
    cookie_env: str,
    browser_port: int,
    refresh_existing: bool,
    promotion_refresh_days: int = 0,
    resume_from_latest: bool = False,
    mutable_refresh_days: int = 4,
    coverage_window_days: int = DEFAULT_COVERAGE_WINDOW_DAYS,
) -> list[list[str]]:
    audit = (
        _coverage_audit(
            spec=spec,
            day=day,
            database_path=database_path,
            window_days=max(coverage_window_days, mutable_refresh_days),
        )
        if resume_from_latest
        else None
    )
    start_day = (
        _resume_start_day(
            spec=spec,
            day=day,
            database_path=database_path,
            mutable_refresh_days=mutable_refresh_days,
            coverage_window_days=coverage_window_days,
        )
        if resume_from_latest
        else day
    )
    retry_recent = (
        resume_from_latest
        and spec.name in LATE_ARRIVING_DATASET_NAMES
        and start_day < day
    )
    command = build_child_command(
        spec,
        day=day,
        start_day=start_day,
        database_path=database_path,
        session_source=session_source,
        cookie_env=cookie_env,
        browser_port=browser_port,
        refresh_existing=refresh_existing or retry_recent or bool(audit and audit.requires_refresh),
        promotion_refresh_days=promotion_refresh_days,
    )
    if spec.name not in {"alimama_adgroup_bidwords", "alimama_promotion_details"}:
        return [command]
    detail_types = (
        ("adgroup", "bidword")
        if spec.name == "alimama_adgroup_bidwords"
        else ("item", "content")
    )
    return [
        [*command, "--detail-type", detail_type]
        for detail_type in detail_types
    ]


def _display_command(command: Sequence[str]) -> str:
    # Do not print environment credentials or any other secret; this is only a
    # human-readable diagnostic representation of the child invocation.
    return subprocess.list2cmdline(list(command))


def _write_run_log(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cleanup_timed_out_crawl_run(
    *,
    database_path: Path,
    label: str,
    day: date,
    timeout: int | None,
) -> str | None:
    """Close the exact active crawl ledger left by a timed-out child."""
    task_types = CRAWL_TASK_TYPES.get(label, ())
    if not task_types:
        return None
    store = CrawlRunStore(database_path)
    error = f"采集子任务超时（{timeout}秒），未收到平台响应。"
    for task_type in task_types:
        run_id = store.fail_running_run_for_timeout(
            store_id=1,
            task_type=task_type,
            business_day=day,
            error_message=error,
        )
        if run_id:
            return run_id
    return None


def run_collection(
    *,
    day: date,
    dataset_names: Sequence[str],
    database_path: Path,
    session_source: str,
    cookie_env: str,
    browser_port: int,
    refresh_existing: bool = False,
    fail_fast: bool = False,
    timeout: int | None = None,
    promotion_refresh_days: int = 0,
    resume_from_latest: bool = False,
    mutable_refresh_days: int = 4,
    coverage_window_days: int = DEFAULT_COVERAGE_WINDOW_DAYS,
    parallelism: int = 2,
) -> tuple[int, dict[str, object]]:
    if parallelism < 1:
        raise ValueError("parallelism must be at least 1")
    specs = selected_specs(dataset_names)
    started_at = datetime.now().astimezone()
    results: list[dict[str, object]] = []
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    jobs: list[tuple[DatasetSpec, list[str], str]] = []
    platform_locks: dict[str, threading.Lock] = {}
    for spec in specs:
        for command in _commands_for_spec(
            spec,
            day=day,
            database_path=database_path,
            session_source=session_source,
            cookie_env=cookie_env,
            browser_port=browser_port,
            refresh_existing=refresh_existing,
            promotion_refresh_days=promotion_refresh_days,
            resume_from_latest=resume_from_latest,
            mutable_refresh_days=mutable_refresh_days,
            coverage_window_days=coverage_window_days,
        ):
            detail = command[-1] if spec.name in {"alimama_adgroup_bidwords", "alimama_promotion_details"} else None
            label = spec.name if detail is None else f"{spec.name}:{detail}"
            jobs.append((spec, command, label))

    def execute(job: tuple[DatasetSpec, list[str], str]) -> dict[str, object]:
        _spec, command, label = job
        lock = platform_locks.setdefault(
            _spec.platform_group or _spec.name, threading.Lock()
        )
        print(f"[{label}] collecting {day.isoformat()} ...", flush=True)
        try:
            with lock:
                completed = subprocess.run(
                    command,
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=child_env,
                    timeout=timeout,
                    check=False,
                )
            result: dict[str, object] = {
                "dataset": label,
                "status": "completed" if completed.returncode == 0 else "failed",
                "returncode": completed.returncode,
                "stdout": completed.stdout[-12000:],
                "stderr": completed.stderr[-12000:],
            }
        except subprocess.TimeoutExpired as exc:
            cleaned_run_id = _cleanup_timed_out_crawl_run(
                database_path=database_path,
                label=label,
                day=day,
                timeout=timeout,
            )
            result = {
                "dataset": label,
                "status": "failed",
                "returncode": None,
                "error": f"timed out after {timeout} seconds",
                "crawl_run_id": cleaned_run_id,
                "stdout": (exc.stdout or "")[-12000:],
                "stderr": (exc.stderr or "")[-12000:],
            }
        if result["status"] == "completed":
            print(f"[{label}] completed", flush=True)
        else:
            detail = str(result.get("error") or result.get("stderr") or result.get("stdout") or "")
            detail_lines = [line.strip() for line in detail.splitlines() if line.strip()]
            concise_detail = detail_lines[-1][:320] if detail_lines else "子任务未返回错误详情"
            print(f"[{label}] failed: {concise_detail}", flush=True)
        return result

    if parallelism == 1 or fail_fast or len(jobs) <= 1:
        for job in jobs:
            result = execute(job)
            results.append(result)
            if fail_fast and result["status"] != "completed":
                break
    else:
        # The browser adapter gives every worker its own tab and SQLite runs in
        # WAL mode.  A small bounded pool keeps independent datasets moving
        # without opening one tab/process per dataset or overwhelming the
        # platform and local database with burst traffic.
        with ThreadPoolExecutor(max_workers=min(parallelism, len(jobs)), thread_name_prefix="daily-collector") as executor:
            future_positions = {
                executor.submit(execute, job): index
                for index, job in enumerate(jobs)
            }
            ordered_results: list[dict[str, object] | None] = [None] * len(jobs)
            for future in as_completed(future_positions):
                ordered_results[future_positions[future]] = future.result()
            results.extend(result for result in ordered_results if result is not None)

    failed = [item for item in results if item["status"] != "completed"]
    summary: dict[str, object] = {
        "business_day": day.isoformat(),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "datasets": list(dataset_names),
        "completed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }
    return (1 if failed else 0), summary


def main(argv: Sequence[str] | None = None) -> int:
    # Windows services and redirected PowerShell processes commonly default to
    # GBK.  Collection summaries can contain replacement characters from a
    # failed child, which GBK cannot encode; force stable UTF-8 output so the
    # persisted batch status is not turned into an outer worker failure.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Collect persisted EchoMerch datasets for one business day (defaults to yesterday)."
    )
    parser.add_argument(
        "--day",
        type=_parse_day_argument,
        default=yesterday_in_shanghai(),
        help="Business day: YYYY-MM-DD, today, or yesterday (default: yesterday).",
    )
    parser.add_argument(
        "--coverage-window-days",
        type=int,
        default=int(os.getenv("ECHO_COLLECTION_COVERAGE_WINDOW_DAYS", str(DEFAULT_COVERAGE_WINDOW_DAYS))),
        help="Bounded observed history used to find missed business days (default: 30).",
    )
    parser.add_argument(
        "--datasets",
        type=_parse_dataset_names,
        default=list(DEFAULT_DATASET_NAMES),
        metavar="NAME[,NAME...]",
        help="Comma-separated dataset names, or all (default: all persisted datasets).",
    )
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--session-source", choices=("env", "drissionpage"), default=os.getenv("ECHO_TMALL_SESSION_SOURCE", "drissionpage"))
    parser.add_argument("--cookie-env", default=os.getenv("ECHO_TMALL_COOKIE_ENV", "SYCM_COOKIE"))
    parser.add_argument("--browser-port", type=int, default=int(os.getenv("ECHO_TMALL_BROWSER_PORT", "9222")))
    parser.add_argument("--refresh-existing", action="store_true", help="Re-fetch rows that already exist for the day.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed dataset.")
    parser.add_argument("--timeout", type=int, help="Optional timeout per child worker in seconds.")
    parser.add_argument(
        "--promotion-refresh-days",
        type=int,
        default=0,
        help="For promotion datasets, replace this many trailing days ending at --day.",
    )
    parser.add_argument(
        "--resume-from-latest",
        action="store_true",
        help="For each dataset, resume after its latest stored day and replay late-arriving report days.",
    )
    parser.add_argument(
        "--mutable-refresh-days",
        type=int,
        default=4,
        help="Trailing days to refresh for delayed BYBT, content, new-customer, and flash-sale reports.",
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=max(1, int(os.getenv("ECHO_COLLECTION_PARALLELISM", "2"))),
        help="Maximum child workers to run concurrently (default: 2; use 1 for strict serial execution).",
    )
    parser.add_argument("--plan", action="store_true", help="Print the resolved plan without starting workers.")
    parser.add_argument("--list-datasets", action="store_true", help="List available dataset names and exit.")
    args = parser.parse_args(argv)

    if args.list_datasets:
        for item in DATASETS:
            print(f"{item.name}\t{item.description}")
        return 0
    if args.browser_port < 1 or args.browser_port > 65535:
        parser.error("--browser-port must be between 1 and 65535")
    if args.promotion_refresh_days < 0:
        parser.error("--promotion-refresh-days must be zero or positive")
    if args.mutable_refresh_days < 1:
        parser.error("--mutable-refresh-days must be at least one")
    if args.coverage_window_days < 1 or args.coverage_window_days > 180:
        parser.error("--coverage-window-days must be between 1 and 180")
    if args.parallelism < 1 or args.parallelism > 8:
        parser.error("--parallelism must be between 1 and 8")
    args.database_path = args.database_path.expanduser().resolve()
    specs = selected_specs(args.datasets)
    commands = [
        _display_command(command)
        for spec in specs
        for command in _commands_for_spec(
            spec,
            day=args.day,
            database_path=args.database_path,
            session_source=args.session_source,
            cookie_env=args.cookie_env,
            browser_port=args.browser_port,
            refresh_existing=args.refresh_existing,
            promotion_refresh_days=args.promotion_refresh_days,
            resume_from_latest=args.resume_from_latest,
            mutable_refresh_days=args.mutable_refresh_days,
            coverage_window_days=args.coverage_window_days,
        )
    ]
    plan = {
        "business_day": args.day.isoformat(),
        "timezone": "Asia/Shanghai",
        "database_path": str(args.database_path),
        "session_source": args.session_source,
        "datasets": list(args.datasets),
        "resume_from_latest": args.resume_from_latest,
        "coverage_window_days": args.coverage_window_days,
        "parallelism": args.parallelism,
        "commands": commands,
    }
    if args.plan:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    status, summary = run_collection(
        day=args.day,
        dataset_names=args.datasets,
        database_path=args.database_path,
        session_source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
        refresh_existing=args.refresh_existing,
        fail_fast=args.fail_fast,
        timeout=args.timeout,
        promotion_refresh_days=args.promotion_refresh_days,
        resume_from_latest=args.resume_from_latest,
        mutable_refresh_days=args.mutable_refresh_days,
        coverage_window_days=args.coverage_window_days,
        parallelism=args.parallelism,
    )
    log_dir = args.database_path.parent / "daily_collection"
    log_path = log_dir / (
        f"collect_{args.day.strftime('%Y%m%d')}_"
        f"{datetime.now().astimezone():%H%M%S}.json"
    )
    summary["log_path"] = str(log_path)
    _write_run_log(log_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
