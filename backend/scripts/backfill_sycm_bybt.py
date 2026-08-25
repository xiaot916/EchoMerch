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
from scripts.fetch_sycm_bybt import fetch_sycm_bybt  # noqa: E402


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "sycm_bybt_backfill"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill SYCM BYBT overview data day by day.")
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--token", default="")
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

    days = _days(args.start, args.end)
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_store_daily_bybt_{_stamp()}.jsonl"
    session = (
        resolve_runtime_session(
            source=args.session_source,
            cookie_env=args.cookie_env,
            browser_port=args.browser_port,
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
        task_type="sycm_bybt",
        start_day=args.start,
        end_day=args.end,
        mode="refresh" if args.refresh_existing else "backfill",
        planned_days=len(days),
        log_file=log_path,
    )
    summary: dict[str, Any] = {"run_id": run_id, "total": len(days), "inserted": 0, "skipped": 0, "failed": 0, "log_path": str(log_path)}
    consecutive_failures = 0
    stopped = False
    try:
        for index, day in enumerate(days, start=1):
            if not args.refresh_existing and day in existing:
                summary["skipped"] += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="skipped_existing")
                print(f"[{index}/{len(days)}] {day.isoformat()} skipped existing")
                continue
            output = args.output_dir / f"{day.isoformat()}.json"
            try:
                fetched = fetch_sycm_bybt(
                    day=day,
                    output=output,
                    cookie=session.cookie_header if session else "",
                    token=args.token,
                    timeout=args.timeout,
                )
                if not fetched.ok:
                    raise RuntimeError(f"fetch failed: HTTP {fetched.status}, code {fetched.code}, message {fetched.message}")
                result = warehouse.ingest_sycm_bybt(
                    source_path=output,
                    business_day=day,
                    store_name=args.store_name,
                    platform_store_id=args.platform_store_id,
                    http_status=fetched.status,
                )
                summary["inserted"] += 1
                consecutive_failures = 0
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingested", metric_count=result.metric_count)
                _log(log_path, {"day": day.isoformat(), "status": "ingested", "fetch": asdict(fetched), "metric_count": result.metric_count})
                print(f"[{index}/{len(days)}] {day.isoformat()} ingested {result.metric_count} metrics")
            except Exception as exc:
                summary["failed"] += 1
                consecutive_failures += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingest_failed", error_message=str(exc))
                _log(log_path, {"day": day.isoformat(), "status": "failed", "error": str(exc)})
                print(f"[{index}/{len(days)}] {day.isoformat()} failed: {exc}")
                if consecutive_failures >= args.max_consecutive_failures:
                    stopped = True
                    print("Stopped after consecutive failures.")
                    break
                continue
            if index < len(days):
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))
    finally:
        runs.finish_run(run_id=run_id, status="stopped" if stopped else "completed_with_errors" if summary["failed"] else "completed", success_days=summary["inserted"], skipped_days=summary["skipped"], failed_days=summary["failed"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _parse_day(value: str) -> date:
    value = value.strip().lower()
    if value == "yesterday":
        return datetime.now().astimezone().date() - timedelta(days=1)
    return date.fromisoformat(value)


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _existing_days(database: LocalDatabase, store_id: int) -> set[date]:
    conn = database.connect()
    try:
        rows = conn.execute(
            f"""
            select {q(BUSINESS_DAY)}
            from store_daily_bybt_overviews
            where {q(STORE_ID)} = ?
              and "百补访客数" is not null
              and "百补支付买家数" is not null
              and "百补支付金额" is not null
              and "百补子订单数" is not null
              and "百补支付成交件数" is not null
            """,
            (store_id,),
        ).fetchall()
    finally:
        conn.close()
    return {date.fromisoformat(str(row[0])) for row in rows}


def _log(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"BYBT backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
