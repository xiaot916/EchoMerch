from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import BUSINESS_DAY, STORE_ID, LocalDatabase, q  # noqa: E402
from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_brandsearch_runtime_context,
)
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.brandsearch_report import BrandSearchPayloadError, load_and_parse  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_brandsearch_report import (  # noqa: E402
    BRANDSEARCH_REPORT_HOME,
    DEFAULT_PRODUCT_ID,
    fetch_brandsearch_report,
)


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = (
    Path(settings.local_database_path).parent / "raw_responses" / "brandsearch_backfill"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill PZ brand-zone daily reports.")
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--product-id", default=DEFAULT_PRODUCT_ID)
    parser.add_argument("--csrf-id", default="")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep-min", type=float, default=1.2)
    parser.add_argument("--sleep-max", type=float, default=2.8)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    args.database_path = args.database_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()

    if args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    if args.sleep_min < 0 or args.sleep_max < args.sleep_min:
        raise ValueError("sleep range must be valid.")
    if not args.product_id:
        raise ValueError("--product-id cannot be empty.")

    days = _days(args.start, args.end)
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_store_daily_brand_zone_{_stamp()}.jsonl"
    runtime = (
        resolve_brandsearch_runtime_context(
            source=args.session_source,
            cookie_env=args.cookie_env,
            csrf_id=args.csrf_id,
            browser_port=args.browser_port,
            report_home_url=BRANDSEARCH_REPORT_HOME.replace(DEFAULT_PRODUCT_ID, args.product_id),
            timeout=args.timeout,
        )
        if pending
        else None
    )
    warehouse = WarehouseStore(args.database_path)
    runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
    )
    run_id = runs.create_run(
        store_id=args.store_id,
        task_type="brandsearch_report",
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
        "log_path": str(log_path),
    }
    failures = 0
    stopped = False
    try:
        for index, business_day in enumerate(days, start=1):
            if not args.refresh_existing and business_day in existing:
                summary["skipped"] += 1
                runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=business_day,
                    status="skipped_existing",
                )
                print(f"[{index}/{len(days)}] {business_day.isoformat()} skipped existing")
                continue
            output = args.output_dir / f"brandsearch_{business_day.isoformat()}.json"
            try:
                status, _code, message, body_size = fetch_brandsearch_report(
                    business_day=business_day,
                    output=output,
                    cookie=runtime.session.cookie_header if runtime else "",
                    csrf_id=runtime.csrf_id if runtime else "",
                    product_id=args.product_id,
                    query_params=dict(runtime.query_params) if runtime else {},
                    timeout=args.timeout,
                )
                if not 200 <= status < 300:
                    raise RuntimeError(f"fetch failed: HTTP {status}, message {message}")
                parsed = load_and_parse(
                    output,
                    business_day,
                    fallback_platform_store_id=args.platform_store_id,
                )
                result = warehouse.ingest_brandsearch_report(
                    source_path=output,
                    business_day=business_day,
                    store_name=args.store_name,
                    platform_store_id=args.platform_store_id,
                    http_status=status,
                )
                summary["inserted"] += 1
                failures = 0
                runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=business_day,
                    status="ingested",
                    metric_count=result.metric_count,
                )
                _log(
                    log_path,
                    {
                        "day": business_day.isoformat(),
                        "status": "ingested",
                        "metrics": parsed.metric_count,
                        "bytes": body_size,
                        "output": str(output),
                    },
                )
                print(
                    f"[{index}/{len(days)}] {business_day.isoformat()} ingested "
                    f"{result.metric_count} metrics"
                )
            except Exception as exc:
                summary["failed"] += 1
                failures += 1
                runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=business_day,
                    status="ingest_failed",
                    error_message=str(exc),
                )
                _log(log_path, {"day": business_day.isoformat(), "status": "failed", "error": str(exc)})
                print(f"[{index}/{len(days)}] {business_day.isoformat()} failed: {exc}")
                if failures >= args.max_consecutive_failures:
                    stopped = True
                    print("Stopped after consecutive failures.")
                    break
                continue
            if index < len(days):
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))
    finally:
        runs.finish_run(
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


def _existing_days(database: LocalDatabase, store_id: int) -> set[date]:
    conn = database.connect()
    try:
        rows = conn.execute(
            f"select {q(BUSINESS_DAY)} from store_daily_brand_zone_overviews "
            f"where {q(STORE_ID)}=?",
            (store_id,),
        ).fetchall()
    finally:
        conn.close()
    return {date.fromisoformat(str(row[0])) for row in rows}


def _parse_day(value: str) -> date:
    value = value.strip().lower()
    if value == "yesterday":
        return datetime.now().astimezone().date() - timedelta(days=1)
    return date.fromisoformat(value)


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _log(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, BrandSearchPayloadError) as exc:
        print(f"Brand-search backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
