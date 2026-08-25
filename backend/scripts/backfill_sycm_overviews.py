from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import BUSINESS_DAY, STORE_ID, LocalDatabase, q  # noqa: E402
from app.modules.imports.crawl_run_store import (  # noqa: E402
    CrawlRunAlreadyRunning,
    CrawlRunStore,
)
from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_sycm_overview import FetchResult, fetch_sycm_overview  # noqa: E402


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = (
    Path(settings.local_database_path).parent
    / "raw_responses"
    / "sycm_overview_backfill"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill SYCM overview rows into store_daily_overviews."
    )
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    add_session_source_arguments(parser)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep-min", type=float, default=1.2)
    parser.add_argument("--sleep-max", type=float, default=2.8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--reuse-response-files", action="store_true")
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path(settings.local_database_path),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    args = parser.parse_args()
    args.database_path = args.database_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()

    if args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    if args.sleep_min < 0 or args.sleep_max < 0 or args.sleep_max < args.sleep_min:
        raise ValueError("--sleep-min and --sleep-max must be a valid range.")

    days = list(_iter_days(args.start, args.end))
    if args.limit is not None:
        days = days[: args.limit]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "days": [day.isoformat() for day in days],
                    "database_path": str(args.database_path),
                    "output_dir": str(args.output_dir),
                    "skip_existing": not args.refresh_existing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_store_daily_overviews_{_timestamp()}.jsonl"
    LocalDatabase(args.database_path).initialize_schema()
    warehouse = WarehouseStore(args.database_path)
    crawl_runs = CrawlRunStore(args.database_path)
    existing_days = _existing_overview_days(args.database_path, store_id=args.store_id)
    planned_fetch_days = [
        day for day in days if args.refresh_existing or day not in existing_days
    ]
    session = None
    if planned_fetch_days:
        session = resolve_runtime_session(
            source=args.session_source,
            cookie_env=args.cookie_env,
            browser_port=args.browser_port,
        )

    crawl_runs.ensure_store_reference(
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
    )
    run_id = crawl_runs.create_run(
        store_id=args.store_id,
        task_type="sycm_overview",
        start_day=args.start,
        end_day=args.end,
        mode="backfill",
        planned_days=len(days),
        log_file=log_path,
    )

    summary: dict[str, Any] = {
        "run_id": run_id,
        "total": len(days),
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
        "log_path": str(log_path),
    }
    consecutive_failures = 0
    stopped_early = False

    try:
        for index, day in enumerate(days, start=1):
            response_path = _response_path(args.output_dir, day)
            if not args.refresh_existing and day in existing_days:
                summary["skipped"] += 1
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="skipped_existing",
                )
                _write_log(
                    log_path,
                    {
                        "run_id": run_id,
                        "day": day.isoformat(),
                        "status": "skipped_existing",
                        "response_file": str(response_path),
                    },
                )
                print(f"[{index}/{len(days)}] {day.isoformat()} skipped existing")
                continue

            try:
                if args.reuse_response_files and response_path.exists():
                    fetch_result = FetchResult(
                        status=200,
                        code=0,
                        message="reused response file",
                        output=str(response_path),
                        bytes=response_path.stat().st_size,
                    )
                else:
                    fetch_result = fetch_sycm_overview(
                        day=day,
                        output=response_path,
                        cookie=session.cookie_header if session else "",
                        token=args.token,
                        timeout=args.timeout,
                    )

                if not fetch_result.ok:
                    summary["failed"] += 1
                    consecutive_failures += 1
                    error_message = fetch_result.message or str(fetch_result.status)
                    crawl_runs.record_day(
                        run_id=run_id,
                        store_id=args.store_id,
                        business_day=day,
                        status="fetch_failed",
                        error_message=error_message,
                    )
                    _write_log(
                        log_path,
                        {
                            "run_id": run_id,
                            "day": day.isoformat(),
                            "status": "fetch_failed",
                            "fetch": asdict(fetch_result),
                        },
                    )
                    print(
                        f"[{index}/{len(days)}] {day.isoformat()} fetch failed: "
                        f"{error_message}"
                    )
                    if _looks_like_session_error(fetch_result):
                        print("Stopped because the login/session response is not usable.")
                        stopped_early = True
                        break
                    if consecutive_failures >= args.max_consecutive_failures:
                        print("Stopped after consecutive failures.")
                        stopped_early = True
                        break
                    continue

                result = warehouse.ingest_sycm_overview(
                    source_path=response_path,
                    business_day=day,
                    store_name=args.store_name,
                    http_status=fetch_result.status,
                )
                summary["inserted"] += 1
                consecutive_failures = 0
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="ingested",
                    metric_count=result.metric_count,
                )
                _write_log(
                    log_path,
                    {
                        "run_id": run_id,
                        "day": day.isoformat(),
                        "status": "ingested",
                        "fetch": asdict(fetch_result),
                        "store_id": result.store.store_id,
                        "metric_count": result.metric_count,
                    },
                )
                print(
                    f"[{index}/{len(days)}] {day.isoformat()} ingested "
                    f"{result.metric_count} metrics"
                )
                existing_days.add(day)
            except Exception as exc:
                summary["failed"] += 1
                consecutive_failures += 1
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="ingest_failed",
                    error_message=str(exc),
                )
                _write_log(
                    log_path,
                    {
                        "run_id": run_id,
                        "day": day.isoformat(),
                        "status": "ingest_failed",
                        "error": str(exc),
                        "response_file": str(response_path),
                    },
                )
                print(f"[{index}/{len(days)}] {day.isoformat()} failed: {exc}")
                if consecutive_failures >= args.max_consecutive_failures:
                    print("Stopped after consecutive failures.")
                    stopped_early = True
                    break
                continue

            if index < len(days):
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))
    finally:
        if stopped_early:
            final_status = "stopped"
        elif summary["failed"]:
            final_status = "completed_with_errors"
        else:
            final_status = "completed"
        crawl_runs.finish_run(
            run_id=run_id,
            status=final_status,
            success_days=summary["inserted"],
            skipped_days=summary["skipped"],
            failed_days=summary["failed"],
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _parse_day(value: str) -> date:
    lowered = value.strip().lower()
    today = datetime.now().astimezone().date()
    if lowered == "today":
        return today
    if lowered == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(value)


def _iter_days(start: date, end: date) -> list[date]:
    current = start
    days: list[date] = []
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _existing_overview_days(database_path: Path, *, store_id: int) -> set[date]:
    conn = LocalDatabase(database_path).connect()
    try:
        rows = conn.execute(
            f"select {q(BUSINESS_DAY)} as business_day "
            f"from store_daily_overviews where {q(STORE_ID)} = ?",
            (store_id,),
        ).fetchall()
    finally:
        conn.close()
    return {date.fromisoformat(row["business_day"]) for row in rows}


def _response_path(output_dir: Path, day: date) -> Path:
    return (
        output_dir
        / f"{day.year:04d}"
        / f"{day.month:02d}"
        / f"sycm_overview_{day.strftime('%Y%m%d')}.json"
    )


def _write_log(path: Path, event: dict[str, Any]) -> None:
    event = {
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        **event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def _looks_like_session_error(result: FetchResult) -> bool:
    message = (result.message or "").lower()
    if result.code is None:
        return True
    return any(
        marker in message
        for marker in (
            "login",
            "session",
            "token",
            "auth",
            "登录",
            "未登录",
            "令牌",
            "权限",
            "验证码",
        )
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CrawlRunAlreadyRunning, OSError, ValueError, sqlite3.Error) as exc:
        print(f"Backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
