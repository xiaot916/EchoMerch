from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import LocalDatabase  # noqa: E402
from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402
from app.modules.imports.crawl_run_store import CrawlRunAlreadyRunning, CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_sycm_activity_calendar import FetchResult, fetch_sycm_activity_calendar  # noqa: E402


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = (
    Path(settings.local_database_path).parent
    / "raw_responses"
    / "sycm_activity_calendar"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect and replace one SYCM activity calendar snapshot per requested year."
    )
    parser.add_argument("--start", type=_parse_day)
    parser.add_argument("--end", type=_parse_day)
    parser.add_argument(
        "--years",
        type=_parse_years,
        help="Comma-separated calendar years. Defaults to the current year and previous two years.",
    )
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep-min", type=float, default=1.2)
    parser.add_argument("--sleep-max", type=float, default=2.8)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--reuse-response-files", action="store_true")
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    args.database_path = args.database_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    _validate(args)

    years = _years_for_args(args.start, args.end, args.years)
    run_start = date(years[0], 1, 1)
    run_end = date(years[-1], 12, 31)
    LocalDatabase(args.database_path).initialize_schema()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_sycm_activity_calendar_{_stamp()}.jsonl"
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
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
        task_type="sycm_activity_calendar",
        start_day=run_start,
        end_day=run_end,
        mode="refresh",
        planned_days=len(years),
        log_file=log_path,
    )
    summary: dict[str, Any] = {
        "run_id": run_id,
        "years": years,
        "total": len(years),
        "inserted": 0,
        "failed": 0,
        "log_path": str(log_path),
    }
    consecutive_failures = 0
    stopped_early = False
    try:
        for index, year in enumerate(years, start=1):
            query_day = date(year, 1, 1)
            response_path = _response_path(args.output_dir, year)
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
                    fetch_result = fetch_sycm_activity_calendar(
                        day=query_day,
                        output=response_path,
                        cookie=session.cookie_header,
                        token=args.token,
                        timeout=args.timeout,
                    )
                if not fetch_result.ok:
                    raise RuntimeError(
                        "fetch failed: "
                        f"HTTP {fetch_result.status}, code {fetch_result.code}, "
                        f"message {fetch_result.message}"
                    )

                result = warehouse.ingest_sycm_activity_calendar(
                    source_path=response_path,
                    business_day=query_day,
                    store_name=args.store_name,
                    platform_store_id=args.platform_store_id,
                    http_status=fetch_result.status,
                    replace_year=year,
                )
                summary["inserted"] += 1
                consecutive_failures = 0
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=query_day,
                    status="ingested",
                    metric_count=result.metric_count,
                )
                _log(
                    log_path,
                    {
                        "run_id": run_id,
                        "year": year,
                        "query_day": query_day.isoformat(),
                        "status": "ingested",
                        "fetch": asdict(fetch_result),
                        "metric_count": result.metric_count,
                    },
                )
                print(
                    f"[{index}/{len(years)}] {year} replaced annual "
                    f"activity calendar ({result.metric_count} events)"
                )
            except Exception as exc:
                summary["failed"] += 1
                consecutive_failures += 1
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=query_day,
                    status="ingest_failed",
                    error_message=str(exc),
                )
                _log(
                    log_path,
                    {
                        "run_id": run_id,
                        "year": year,
                        "query_day": query_day.isoformat(),
                        "status": "failed",
                        "error": str(exc),
                        "response_file": str(response_path),
                    },
                )
                print(f"[{index}/{len(years)}] {year} failed: {exc}")
                if consecutive_failures >= args.max_consecutive_failures:
                    print("Stopped after consecutive failures.")
                    stopped_early = True
                    break
            if index < len(years):
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))
    finally:
        crawl_runs.finish_run(
            run_id=run_id,
            status=(
                "stopped"
                if stopped_early
                else "completed_with_errors"
                if summary["failed"]
                else "completed"
            ),
            success_days=summary["inserted"],
            skipped_days=0,
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
        return date.fromordinal(today.toordinal() - 1)
    return date.fromisoformat(value)


def _parse_years(value: str) -> list[int]:
    years: list[int] = []
    for part in value.split(","):
        text = part.strip()
        if not text:
            continue
        year = int(text)
        if year < 2000 or year > 9999:
            raise argparse.ArgumentTypeError("years must be four-digit calendar years")
        years.append(year)
    if not years:
        raise argparse.ArgumentTypeError("--years must contain at least one year")
    return sorted(set(years))


def _years_for_args(
    start: date | None,
    end: date | None,
    requested_years: list[int] | None,
    *,
    today: date | None = None,
) -> list[int]:
    if requested_years:
        return requested_years
    if (start is None) != (end is None):
        raise ValueError("--start and --end must be supplied together.")
    if start is not None and end is not None:
        if end < start:
            raise ValueError("--end must be greater than or equal to --start.")
        return list(range(start.year, end.year + 1))
    current_year = (today or datetime.now().astimezone().date()).year
    return [current_year - 2, current_year - 1, current_year]


def _validate(args: argparse.Namespace) -> None:
    _years_for_args(args.start, args.end, args.years)
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        raise ValueError("--sleep-min and --sleep-max must be a valid range.")
    if args.max_consecutive_failures < 1:
        raise ValueError("--max-consecutive-failures must be at least 1.")


def _response_path(output_dir: Path, year: int) -> Path:
    return (
        output_dir
        / f"{year:04d}"
        / f"sycm_activity_calendar_{year:04d}.json"
    )


def _log(path: Path, value: dict[str, object]) -> None:
    event = {
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        **value,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CrawlRunAlreadyRunning, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"Activity calendar backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
