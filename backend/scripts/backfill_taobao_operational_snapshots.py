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
from app.core.local_database import LocalDatabase, q  # noqa: E402
from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_taobao_operational_snapshots import (  # noqa: E402
    fetch_activity_items,
    fetch_current_prices,
    fetch_risk_price,
)

DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "taobao_operational_snapshots"
ACTIVITY_TYPES = ("bybt_online", "bybt_pending", "flash_sale_online")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and replace Taobao operational item snapshots day by day.")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--current-page-size", type=int, default=500)
    parser.add_argument("--activity-page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--page-sleep", type=float, default=0.35)
    parser.add_argument("--day-sleep-min", type=float, default=1.2)
    parser.add_argument("--day-sleep-max", type=float, default=2.8)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    _validate(args)
    days = _days(args.start, args.end)
    args.database_path = args.database_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    session = resolve_runtime_session(source=args.session_source, cookie_env=args.cookie_env, browser_port=args.browser_port) if pending else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_taobao_operational_snapshots_{_stamp()}.jsonl"
    warehouse = WarehouseStore(args.database_path)
    runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(store_id=args.store_id, store_name=args.store_name, platform_store_id=args.platform_store_id)
    run_id = runs.create_run(store_id=args.store_id, task_type="taobao_operational_snapshots", start_day=args.start, end_day=args.end, mode="refresh" if args.refresh_existing else "backfill", planned_days=len(days), log_file=log_path)
    summary: dict[str, Any] = {"run_id": run_id, "total": len(days), "inserted": 0, "skipped": 0, "failed": 0, "log_path": str(log_path)}
    failures = 0
    stopped = False
    try:
        for index, day in enumerate(days, start=1):
            if not args.refresh_existing and day in existing:
                summary["skipped"] += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="skipped_existing")
                print(f"[{index}/{len(days)}] {day} skipped existing")
                continue
            try:
                risk_path, current_path, activity_path, details = _fetch_day(day, args, session.cookie_header if session else "")
                result = warehouse.ingest_taobao_operational_snapshots(
                    risk_price_path=risk_path,
                    current_price_path=current_path,
                    activity_snapshot_path=activity_path,
                    business_day=day,
                    store_name=args.store_name,
                    platform_store_id=args.platform_store_id,
                )
                summary["inserted"] += 1
                failures = 0
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingested", metric_count=result.metric_count)
                _log(log_path, {"day": day.isoformat(), "status": "ingested", **details})
                print(f"[{index}/{len(days)}] {day} ingested risk/current/activity ({details})")
            except Exception as exc:
                summary["failed"] += 1
                failures += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingest_failed", error_message=str(exc))
                _log(log_path, {"day": day.isoformat(), "status": "failed", "error": str(exc)})
                print(f"[{index}/{len(days)}] {day} failed: {exc}")
                if failures >= args.max_consecutive_failures:
                    stopped = True
                    break
            if index < len(days) and args.day_sleep_max:
                time.sleep(random.uniform(args.day_sleep_min, args.day_sleep_max))
    finally:
        runs.finish_run(run_id=run_id, status="stopped" if stopped else "completed_with_errors" if summary["failed"] else "completed", success_days=summary["inserted"], skipped_days=summary["skipped"], failed_days=summary["failed"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["failed"] else 1


def _fetch_day(day: date, args: argparse.Namespace, cookie: str) -> tuple[Path, Path, Path, dict[str, Any]]:
    directory = args.output_dir / day.isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    risk_output = directory / "risk_price.json"
    risk = fetch_risk_price(output=risk_output, cookie=cookie, timeout=args.timeout)
    if not risk.ok:
        raise RuntimeError(f"risk-price fetch failed: HTTP {risk.status}, code {risk.code}, message {risk.message}")
    current_pages: list[dict[str, Any]] = []
    current_rows = 0
    current_stop = "max_pages"
    for page in range(1, args.max_pages + 1):
        output = directory / f"current_price_{page:04d}.json"
        result = fetch_current_prices(output=output, cookie=cookie, page=page, size=args.current_page_size, timeout=args.timeout)
        if not result.ok:
            raise RuntimeError(f"current-price page {page} fetch failed: HTTP {result.status}, code {result.code}, message {result.message}")
        payload = json.loads(output.read_text(encoding="utf-8"))
        rows, count = _page_metadata(payload)
        current_pages.append(payload)
        current_rows += len(rows)
        if not rows:
            current_stop = "no_more_rows"
            break
        if count is not None and page * args.current_page_size >= count:
            current_stop = "record_count_reached"
            break
        if len(rows) < args.current_page_size:
            current_stop = "short_page"
            break
        if args.page_sleep:
            time.sleep(args.page_sleep)
    current_output = directory / "current_prices.json"
    current_output.write_text(json.dumps({"pages": current_pages}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    activity_snapshots: list[dict[str, Any]] = []
    activity_details: dict[str, Any] = {}
    for snapshot_type in ACTIVITY_TYPES:
        pages: list[dict[str, Any]] = []
        rows_total = 0
        stop = "max_pages"
        for page in range(1, args.max_pages + 1):
            output = directory / f"{snapshot_type}_{page:04d}.json"
            result = fetch_activity_items(output=output, cookie=cookie, snapshot_type=snapshot_type, page=page, page_size=args.activity_page_size, timeout=args.timeout)
            if not result.ok:
                raise RuntimeError(f"{snapshot_type} page {page} fetch failed: HTTP {result.status}, code {result.code}, message {result.message}")
            payload = json.loads(output.read_text(encoding="utf-8"))
            rows, count = _page_metadata(payload)
            pages.append(payload)
            rows_total += len(rows)
            if not rows:
                stop = "no_more_rows"
                break
            if count is not None and page * args.activity_page_size >= count:
                stop = "record_count_reached"
                break
            if len(rows) < args.activity_page_size:
                stop = "short_page"
                break
            if args.page_sleep:
                time.sleep(args.page_sleep)
        activity_snapshots.append({"snapshotType": snapshot_type, "pages": pages})
        activity_details[snapshot_type] = {"rows": rows_total, "stop_reason": stop, "pages": len(pages)}
    activity_output = directory / "activity_item_snapshots.json"
    activity_output.write_text(json.dumps({"snapshots": activity_snapshots}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return risk_output, current_output, activity_output, {"current_rows": current_rows, "current_stop_reason": current_stop, "activity": activity_details}


def _page_metadata(payload: object) -> tuple[list[object], int | None]:
    def find(value: object, depth: int = 0) -> tuple[list[object], int | None]:
        if depth > 6 or not isinstance(value, dict):
            return [], None
        for key in ("items", "data", "list", "rows", "riskDetectRecords"):
            rows = value.get(key)
            if isinstance(rows, list):
                count = next((value.get(key) for key in ("total", "totalCount", "recordCount") if value.get(key) is not None), None)
                try:
                    return rows, int(count) if count is not None else None
                except (TypeError, ValueError):
                    return rows, None
        for key in ("data", "model", "result", "content"):
            found = find(value.get(key), depth + 1)
            if found[0] or found[1] is not None:
                return found
        return [], None
    return find(payload)


def _existing_days(database: LocalDatabase, store_id: int) -> set[date]:
    with database.connect() as conn:
        rows = conn.execute(
            '''
            select "业务日期"
            from "store_daily_taobao_activity_item_snapshots"
            where "店铺ID" = ?
            group by "业务日期"
            union
            select days."业务日期"
            from crawl_run_days as days
            inner join crawl_runs as runs
              on runs."采集任务ID" = days."采集任务ID"
            where days."店铺ID" = ?
              and runs."任务类型" = 'taobao_operational_snapshots'
              and days."日期状态" = 'ingested'
            ''',
            (store_id, store_id),
        ).fetchall()
    return {date.fromisoformat(str(row[0])) for row in rows}


def _validate(args: argparse.Namespace) -> None:
    if args.end < args.start or not 1 <= args.current_page_size <= 500 or not 1 <= args.activity_page_size <= 200 or args.max_pages < 1:
        raise ValueError("invalid date range, page sizes, or max-pages")
    if args.page_sleep < 0 or args.day_sleep_min < 0 or args.day_sleep_max < args.day_sleep_min:
        raise ValueError("sleep values must be valid")


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=index) for index in range((end - start).days + 1)]


def _log(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
