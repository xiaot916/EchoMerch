from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

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
from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_taobao_flash_sale import FLASH_SALE_HOME_URL  # noqa: E402
from scripts.fetch_taobao_flash_sale_items import fetch_taobao_flash_sale_items  # noqa: E402


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "taobao_flash_sale_items_backfill"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Taobao flash-sale item data day by day.")
    parser.add_argument("--start", type=date.fromisoformat, required=True); parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--store-id", type=int, default=1); parser.add_argument("--store-name", default=DEFAULT_STORE_NAME); parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--page-size", type=int, default=50); parser.add_argument("--max-pages", type=int, default=1000); parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--page-sleep", type=float, default=0.35); parser.add_argument("--day-sleep-min", type=float, default=1.2); parser.add_argument("--day-sleep-max", type=float, default=2.8)
    parser.add_argument("--refresh-existing", action="store_true"); parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path)); parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    add_session_source_arguments(parser)
    args = parser.parse_args(); args.database_path = args.database_path.expanduser().resolve(); args.output_dir = args.output_dir.expanduser().resolve()
    if args.end < args.start or not 1 <= args.page_size <= 100 or args.max_pages < 1: raise ValueError("invalid date range, page-size, or max-pages")
    if args.page_sleep < 0 or args.day_sleep_min < 0 or args.day_sleep_max < args.day_sleep_min: raise ValueError("sleep values must be valid")
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    days = _overview_days(database, args.store_id, args.start, args.end)
    if not days:
        raise ValueError("No Taobao flash-sale overview days exist in the requested range.")
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]; args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_store_daily_taobao_flash_sale_items_{_stamp()}.jsonl"
    session = (
        resolve_runtime_session(
            source=args.session_source,
            cookie_env=args.cookie_env,
            browser_port=args.browser_port,
            home_url=FLASH_SALE_HOME_URL,
            platform_name="淘宝秒杀",
            expected_hosts=("myseller.taobao.com",),
        )
        if pending
        else None
    )
    warehouse = WarehouseStore(args.database_path); runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(store_id=args.store_id, store_name=args.store_name, platform_store_id=args.platform_store_id)
    run_id = runs.create_run(store_id=args.store_id, task_type="taobao_flash_sale_items", start_day=args.start, end_day=args.end, mode="refresh" if args.refresh_existing else "backfill", planned_days=len(days), log_file=log_path)
    summary: dict[str, Any] = {"run_id": run_id, "total": len(days), "inserted": 0, "no_data": 0, "skipped": 0, "failed": 0, "log_path": str(log_path)}; failures = 0; stopped = False
    try:
        for index, day in enumerate(days, start=1):
            if not args.refresh_existing and day in existing:
                summary["skipped"] += 1; runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="skipped_existing"); print(f"[{index}/{len(days)}] {day} skipped existing"); continue
            try:
                combined, rows, pages, stop_reason = _fetch_day(day, args, session.cookie_header if session else "")
                result = warehouse.ingest_taobao_flash_sale_items(source_path=combined, business_day=day, store_name=args.store_name, platform_store_id=args.platform_store_id)
                status = "ingested" if rows else "no_data"
                summary["inserted" if rows else "no_data"] += 1; failures = 0
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status=status, metric_count=result.metric_count)
                _log(log_path, {"day": day.isoformat(), "status": status, "rows": rows, "pages": pages, "stop_reason": stop_reason})
                print(f"[{index}/{len(days)}] {day} {status} {rows} rows ({pages} pages, {stop_reason})")
            except Exception as exc:
                summary["failed"] += 1; failures += 1; runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingest_failed", error_message=str(exc)); _log(log_path, {"day": day.isoformat(), "status": "failed", "error": str(exc)}); print(f"[{index}/{len(days)}] {day} failed: {exc}")
                if failures >= args.max_consecutive_failures: stopped = True; break
            if index < len(days): time.sleep(random.uniform(args.day_sleep_min, args.day_sleep_max))
    finally:
        runs.finish_run(run_id=run_id, status="stopped" if stopped else "completed_with_errors" if summary["failed"] else "completed", success_days=summary["inserted"] + summary["no_data"], skipped_days=summary["skipped"], failed_days=summary["failed"])
    print(json.dumps(summary, ensure_ascii=False, indent=2)); return 0 if not summary["failed"] else 1


def _fetch_day(day: date, args: argparse.Namespace, cookie: str) -> tuple[Path, int, int, str]:
    directory = args.output_dir / day.isoformat(); directory.mkdir(parents=True, exist_ok=True); payloads: list[dict[str, object]] = []; total_rows = 0; stop_reason = "max_pages"
    for page in range(1, args.max_pages + 1):
        output = directory / f"page_{page:04d}.json"; result = fetch_taobao_flash_sale_items(day=day, output=output, cookie=cookie, page=page, page_size=args.page_size, timeout=args.timeout)
        if not result.ok: raise RuntimeError(f"page {page} fetch failed: HTTP {result.status}, code {result.code}, message {result.message}")
        payload = json.loads(output.read_text(encoding="utf-8")); page_rows, count = _page_metadata(payload); payloads.append(payload); total_rows += len(page_rows)
        if not page_rows: stop_reason = "no_more_rows"; break
        if count is not None and page * args.page_size >= count: stop_reason = "record_count_reached"; break
        if len(page_rows) < args.page_size: stop_reason = "short_page"; break
        if args.page_sleep: time.sleep(args.page_sleep)
    combined = args.output_dir / f"flash_sale_items_{day.isoformat()}.json"; combined.write_text(json.dumps({"pages": payloads}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"); return combined, total_rows, len(payloads), stop_reason


def _page_metadata(payload: object) -> tuple[list[object], int | None]:
    def find(value: object, depth: int = 0) -> tuple[list[object], int | None]:
        if depth > 4 or not isinstance(value, dict): return [], None
        rows = next((value.get(k) for k in ("data", "list", "rows", "items") if isinstance(value.get(k), list)), None)
        if isinstance(rows, list):
            count = next((value.get(k) for k in ("total", "totalCount", "recordCount") if value.get(k) is not None), None)
            try: return rows, int(count) if count is not None else None
            except (TypeError, ValueError): return rows, None
        for key in ("data", "result", "content"):
            found = find(value.get(key), depth + 1)
            if found[0] or found[1] is not None: return found
        return [], None
    return find(payload)


def _existing_days(database: LocalDatabase, store_id: int) -> set[date]:
    with database.connect() as conn:
        rows = conn.execute(
            f"""
            select {q(BUSINESS_DAY)}
            from store_daily_taobao_flash_sale_items
            where {q(STORE_ID)} = ?
            group by {q(BUSINESS_DAY)}
            union
            select days.{q(BUSINESS_DAY)}
            from crawl_run_days as days
            inner join crawl_runs as runs
              on runs.{q(CRAWL_RUN_ID)} = days.{q(CRAWL_RUN_ID)}
            where days.{q(STORE_ID)} = ?
              and runs.{q(CRAWL_TASK_TYPE)} = 'taobao_flash_sale_items'
              and days.{q(DAY_STATUS)} in ('ingested', 'no_data')
            """,
            (store_id, store_id),
        ).fetchall()
    return {date.fromisoformat(str(row[0])) for row in rows}


def _overview_days(database: LocalDatabase, store_id: int, start: date, end: date) -> list[date]:
    with database.connect() as conn:
        rows = conn.execute(
            f"""
            select {q(BUSINESS_DAY)}
            from store_daily_taobao_flash_sale_overviews
            where {q(STORE_ID)} = ?
              and {q(BUSINESS_DAY)} between ? and ?
            group by {q(BUSINESS_DAY)}
            order by {q(BUSINESS_DAY)}
            """,
            (store_id, start.isoformat(), end.isoformat()),
        ).fetchall()
    return [date.fromisoformat(str(row[0])) for row in rows]


def _log(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
def _stamp() -> str: return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__": raise SystemExit(main())
