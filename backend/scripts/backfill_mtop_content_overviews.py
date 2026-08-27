from __future__ import annotations

import argparse
import json
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
from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_runtime_session,
)
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_mtop_content_overview import (  # noqa: E402
    CONTENT_HOME_URL,
    fetch_mtop_content_overview,
)


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = (
    Path(settings.local_database_path).parent
    / "raw_responses"
    / "mtop_content_overview_backfill"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill MTop content overview data day by day."
    )
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
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
    add_session_source_arguments(parser)
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
                    "skip_existing": not args.refresh_existing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_content_overviews_{_timestamp()}.jsonl"
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing_days = _existing_days(database, args.store_id)
    planned_days = [
        day for day in days if args.refresh_existing or day not in existing_days
    ]
    warehouse = WarehouseStore(args.database_path)
    crawl_runs = CrawlRunStore(args.database_path)
    crawl_runs.ensure_store_reference(
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
    )
    run_id = crawl_runs.create_run(
        store_id=args.store_id,
        task_type="mtop_content_overview",
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
        "no_data": 0,
        "failed": 0,
        "log_path": str(log_path),
    }
    session = None
    if planned_days:
        try:
            session = resolve_runtime_session(
                source=args.session_source,
                cookie_env=args.cookie_env,
                browser_port=args.browser_port,
                home_url=CONTENT_HOME_URL,
                platform_name="内容效果",
                expected_hosts=("web.taobao.com",),
            )
        except Exception as exc:
            # Browser/page preflight used to happen before the crawl ledger was
            # created, so the UI showed a real collection failure as "未到达".
            # Persist every affected day before returning the worker error.
            for day in days:
                if not args.refresh_existing and day in existing_days:
                    summary["skipped"] += 1
                    crawl_runs.record_day(
                        run_id=run_id,
                        store_id=args.store_id,
                        business_day=day,
                        status="skipped_existing",
                    )
                    continue
                summary["failed"] += 1
                crawl_runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="fetch_failed",
                    error_message=str(exc),
                )
                _write_log(
                    log_path,
                    {
                        "day": day.isoformat(),
                        "status": "failed",
                        "error": str(exc),
                        "phase": "session_preflight",
                    },
                )
            crawl_runs.finish_run(
                run_id=run_id,
                status="completed_with_errors",
                success_days=0,
                skipped_days=summary["skipped"],
                failed_days=summary["failed"],
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 1
    consecutive_failures = 0
    stopped = False
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
                print(f"[{index}/{len(days)}] {day.isoformat()} skipped existing")
                continue
            try:
                fetched = fetch_mtop_content_overview(
                    day=day,
                    output=response_path,
                    cookie=session.cookie_header if session else "",
                    timeout=args.timeout,
                )
                if not fetched.ok:
                    raise RuntimeError(
                        f"fetch failed: HTTP {fetched.status}, "
                        f"code {fetched.code}, message {fetched.message}"
                    )
                if not _has_target_row(response_path, day):
                    summary["skipped"] += 1
                    summary["no_data"] += 1
                    crawl_runs.record_day(
                        run_id=run_id,
                        store_id=args.store_id,
                        business_day=day,
                        status="no_data",
                    )
                    _write_log(
                        log_path,
                        {
                            "day": day.isoformat(),
                            "status": "no_data",
                            "fetch": asdict(fetched),
                            "reason": "MTop returned an empty result list for the target day",
                        },
                    )
                    print(f"[{index}/{len(days)}] {day.isoformat()} no data")
                    continue
                result = warehouse.ingest_mtop_content_overview(
                    source_path=response_path,
                    business_day=day,
                    store_name=args.store_name,
                    platform_store_id=args.platform_store_id,
                    http_status=fetched.status,
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
                        "day": day.isoformat(),
                        "status": "ingested",
                        "fetch": asdict(fetched),
                        "metric_count": result.metric_count,
                    },
                )
                print(
                    f"[{index}/{len(days)}] {day.isoformat()} ingested "
                    f"{result.metric_count} metrics"
                )
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
                        "day": day.isoformat(),
                        "status": "failed",
                        "error": str(exc),
                        "response_file": str(response_path),
                    },
                )
                print(f"[{index}/{len(days)}] {day.isoformat()} failed: {exc}")
                if consecutive_failures >= args.max_consecutive_failures:
                    stopped = True
                    print("Stopped after consecutive failures.")
                    break
                continue
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
            f"select {q(BUSINESS_DAY)} from store_daily_content_overviews "
            f"where {q(STORE_ID)}=?",
            (store_id,),
        ).fetchall()
    finally:
        conn.close()
    return {date.fromisoformat(str(row[0])) for row in rows}


def _response_path(output_dir: Path, day: date) -> Path:
    return (
        output_dir
        / f"{day.year:04d}"
        / f"{day.month:02d}"
        / f"mtop_content_overview_{day.strftime('%Y%m%d')}.json"
    )


def _has_target_row(path: Path, day: date) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = (
        payload.get("data", {})
        .get("model", {})
        .get("result", [])
    )
    if not isinstance(rows, list):
        return False
    target = day.strftime("%Y%m%d")
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = row.get("date")
        value = entry.get("absolute") if isinstance(entry, dict) else row.get("ds")
        if str(value or "") == target:
            return True
    return False


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
        print(f"Content overview backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
