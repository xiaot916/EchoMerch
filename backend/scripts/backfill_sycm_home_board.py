from __future__ import annotations

"""Backfill SYCM home board data day by day into ``store_daily_sycm_home_board``.

The home-board group contains 7 supported endpoints. For each
business day this script fetches them and upserts the flat numeric
metrics into the single home-board fact table.
"""

import argparse
import json
import os
import random
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
from app.modules.collection.coverage import REQUIRED_TABLE_FILTERS  # noqa: E402
from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_runtime_session,
)
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_sycm_home_board import (  # noqa: E402
    fetch_sycm_home_board,
)


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = (
    Path(settings.local_database_path).parent
    / "raw_responses"
    / "sycm_home_board_backfill"
)

ENDPOINTS = (
    "grow_factor",
    "grow_trend",
    "month_overview",
    "month_trend",
    "experience_scorecard",
    "main_cate_info",
    "level_info",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill SYCM home board data day by day."
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
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument(
        "--database-path", type=Path, default=Path(settings.local_database_path)
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    args.database_path = args.database_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()

    if args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        raise ValueError("--sleep-min/--sleep-max must be valid.")

    days = _iter_days(args.start, args.end)
    if args.limit is not None:
        days = days[: args.limit]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "days": [day.isoformat() for day in days],
                    "endpoints": list(ENDPOINTS),
                    "skip_existing": not args.refresh_existing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_home_board_{_timestamp()}.jsonl"
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing_days = _existing_days(database, args.store_id)
    planned_days = [
        day for day in days if args.refresh_existing or day not in existing_days
    ]
    session = (
        resolve_runtime_session(
            source=args.session_source,
            cookie_env=args.cookie_env,
            browser_port=args.browser_port,
        )
        if planned_days
        else None
    )
    warehouse = WarehouseStore(args.database_path)
    crawl_runs = CrawlRunStore(args.database_path)
    crawl_runs.ensure_store_reference(
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
    )
    run_id = crawl_runs.create_run(
        store_id=args.store_id,
        task_type="sycm_home_board",
        start_day=args.start,
        end_day=args.end,
        mode="refresh" if args.refresh_existing else "backfill",
        planned_days=len(days),
        log_file=log_path,
    )
    summary: dict[str, Any] = {
        "run_id": run_id,
        "total": len(days),
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
        "endpoints_ok": 0,
        "endpoints_failed": 0,
        "log_path": str(log_path),
    }
    consecutive_failures = 0
    stopped = False
    try:
        for index, day in enumerate(days, start=1):
            day_dir = _day_dir(args.output_dir, day)
            if not args.refresh_existing and day in existing_days:
                summary["skipped"] += 1
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="skipped_existing",
                )
                print(f"[{index}/{len(days)}] {day.isoformat()} skipped existing")
                continue

            day_results = fetch_sycm_home_board(
                day=day,
                output_dir=day_dir,
                cookie=session.cookie_header if session else "",
                token=args.token,
                timeout=args.timeout,
            )

            day_ingested = 0
            day_failed = 0
            day_errors: list[str] = []
            for endpoint_name in ENDPOINTS:
                result = day_results.get(endpoint_name)
                if result is None:
                    day_errors.append(f"{endpoint_name}: missing result")
                    day_failed += 1
                    continue
                if not result.ok:
                    day_errors.append(
                        f"{endpoint_name}: HTTP {result.status}, "
                        f"code {result.code}, {result.message}"
                    )
                    day_failed += 1
                    continue
                try:
                    warehouse.ingest_sycm_home_board(
                        source_path=Path(result.output),
                        business_day=day,
                        store_name=args.store_name,
                        endpoint_name=endpoint_name,
                        http_status=result.status,
                    )
                    day_ingested += 1
                    summary["endpoints_ok"] += 1
                except Exception as exc:
                    day_errors.append(f"{endpoint_name}: ingest {exc}")
                    day_failed += 1
                    summary["endpoints_failed"] += 1

            if day_failed == 0 and day_ingested == len(ENDPOINTS) and day in _existing_days(database, args.store_id):
                summary["inserted"] += 1
                consecutive_failures = 0
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="ingested",
                    metric_count=day_ingested,
                )
                print(
                    f"[{index}/{len(days)}] {day.isoformat()} ingested "
                    f"{day_ingested}/{len(ENDPOINTS)} endpoints"
                )
                _write_log(
                    log_path,
                    {
                        "day": day.isoformat(),
                        "status": "ingested",
                        "endpoints_ok": day_ingested,
                    },
                )
            else:
                if day_failed == 0:
                    day_errors.append("首页核心体验指标或主营类目缺失，已保留原始响应供排查")
                    summary["endpoints_failed"] += 1
                summary["failed"] += 1
                consecutive_failures += 1
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="ingest_failed",
                    error_message="; ".join(day_errors[:5]),
                )
                _write_log(
                    log_path,
                    {
                        "day": day.isoformat(),
                        "status": "failed",
                        "errors": day_errors,
                    },
                )
                print(f"[{index}/{len(days)}] {day.isoformat()} partial: {day_errors[:3]}")
                if consecutive_failures >= args.max_consecutive_failures:
                    stopped = True
                    print("Stopped after consecutive failures.")
                    break
            if index < len(days):
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))
    finally:
        crawl_runs.finish_run(
            run_id=run_id,
            status=(
                "stopped"
                if stopped
                else "completed_with_errors"
                if summary["failed"]
                else "completed"
            ),
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
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _existing_days(database: LocalDatabase, store_id: int) -> set[date]:
    conn = database.connect()
    try:
        rows = conn.execute(
            f"select {q(BUSINESS_DAY)} from store_daily_sycm_home_board "
            f"where {q(STORE_ID)}=?"
            + REQUIRED_TABLE_FILTERS["store_daily_sycm_home_board"],
            (store_id,),
        ).fetchall()
    finally:
        conn.close()
    return {date.fromisoformat(str(row[0])) for row in rows}


def _day_dir(output_dir: Path, day: date) -> Path:
    return output_dir / f"{day.year:04d}" / f"{day.month:02d}" / day.isoformat()


def _write_log(path: Path, event: dict[str, Any]) -> None:
    payload = {
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        **event,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Home board backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
