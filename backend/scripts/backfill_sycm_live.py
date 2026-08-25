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
from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_sycm_live import (  # noqa: E402
    fetch_live_overview,
    fetch_live_store_performance,
    fetch_live_talent_page,
)


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "sycm_live_backfill"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill SYCM live reports day by day.")
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--token", default="")
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--page-sleep", type=float, default=0.2)
    parser.add_argument("--day-sleep-min", type=float, default=1.1)
    parser.add_argument("--day-sleep-max", type=float, default=2.1)
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
    if not 1 <= args.page_size <= 100 or args.max_pages < 1:
        raise ValueError("page-size must be 1..100 and max-pages must be positive.")
    if args.page_sleep < 0 or args.day_sleep_min < 0 or args.day_sleep_max < args.day_sleep_min:
        raise ValueError("sleep values must be valid.")

    days = _days(args.start, args.end)
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_store_daily_live_{_stamp()}.jsonl"
    session = resolve_runtime_session(source=args.session_source, cookie_env=args.cookie_env, browser_port=args.browser_port) if pending else None
    warehouse = WarehouseStore(args.database_path)
    runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(store_id=args.store_id, store_name=args.store_name, platform_store_id=args.platform_store_id)
    run_id = runs.create_run(store_id=args.store_id, task_type="sycm_live", start_day=args.start, end_day=args.end, mode="refresh" if args.refresh_existing else "backfill", planned_days=len(days), log_file=log_path)
    summary: dict[str, Any] = {"run_id": run_id, "total": len(days), "inserted": 0, "skipped": 0, "failed": 0, "log_path": str(log_path)}
    failures = 0
    stopped = False
    try:
        for index, day in enumerate(days, start=1):
            if not args.refresh_existing and day in existing:
                summary["skipped"] += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="skipped_existing")
                print(f"[{index}/{len(days)}] {day.isoformat()} skipped existing")
                continue
            try:
                overview_path, store_path, talent_path, talent_pages = _fetch_day(day, args, session.cookie_header if session else "")
                overview = warehouse.ingest_sycm_live_overview(source_path=overview_path, business_day=day, store_name=args.store_name, platform_store_id=args.platform_store_id)
                store = warehouse.ingest_sycm_live_store_performance(source_path=store_path, business_day=day, store_name=args.store_name, platform_store_id=args.platform_store_id)
                talent = warehouse.ingest_sycm_live_talent(source_path=talent_path, business_day=day, store_name=args.store_name, platform_store_id=args.platform_store_id)
                metric_count = overview.metric_count + store.metric_count + talent.metric_count
                summary["inserted"] += 1
                failures = 0
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingested", metric_count=metric_count)
                _log(log_path, {"day": day.isoformat(), "status": "ingested", "overview_metrics": overview.metric_count, "store_metrics": store.metric_count, "talent_rows": talent.metric_count, "talent_pages": talent_pages})
                print(f"[{index}/{len(days)}] {day.isoformat()} ingested overview={overview.metric_count}, store={store.metric_count}, talent={talent.metric_count} ({talent_pages} pages)")
            except Exception as exc:
                summary["failed"] += 1
                failures += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingest_failed", error_message=str(exc))
                _log(log_path, {"day": day.isoformat(), "status": "failed", "error": str(exc)})
                print(f"[{index}/{len(days)}] {day.isoformat()} failed: {exc}")
                if failures >= args.max_consecutive_failures:
                    stopped = True
                    print("Stopped after consecutive failures.")
                    break
                continue
            if index < len(days):
                time.sleep(random.uniform(args.day_sleep_min, args.day_sleep_max))
    finally:
        runs.finish_run(run_id=run_id, status="stopped" if stopped else "completed_with_errors" if summary["failed"] else "completed", success_days=summary["inserted"], skipped_days=summary["skipped"], failed_days=summary["failed"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _fetch_day(day: date, args: argparse.Namespace, cookie: str) -> tuple[Path, Path, Path, int]:
    day_dir = args.output_dir / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    overview_path = day_dir / "overview.json"
    store_path = day_dir / "store_performance.json"
    overview_fetch = fetch_live_overview(day=day, output=overview_path, cookie=cookie, token=args.token, timeout=args.timeout)
    store_fetch = fetch_live_store_performance(day=day, output=store_path, cookie=cookie, token=args.token, timeout=args.timeout)
    if not overview_fetch.ok or not store_fetch.ok:
        raise RuntimeError(f"summary fetch failed: overview={asdict(overview_fetch)}, store={asdict(store_fetch)}")
    talent_payloads: list[dict[str, object]] = []
    talent_pages = 0
    for page in range(1, args.max_pages + 1):
        page_path = day_dir / f"talent_page_{page:04d}.json"
        fetched = fetch_live_talent_page(day=day, output=page_path, cookie=cookie, page=page, page_size=args.page_size, token=args.token, timeout=args.timeout)
        if not fetched.ok:
            raise RuntimeError(f"talent page {page} fetch failed: {asdict(fetched)}")
        payload = json.loads(page_path.read_text(encoding="utf-8"))
        page_rows, record_count = _talent_page_metadata(payload)
        talent_payloads.append(payload)
        talent_pages = page
        if not page_rows or (record_count is not None and page * args.page_size >= record_count) or len(page_rows) < args.page_size:
            break
        if args.page_sleep:
            time.sleep(args.page_sleep)
    else:
        raise RuntimeError("live talent pagination exceeded --max-pages")
    talent_path = day_dir / "talent.json"
    talent_path.write_text(json.dumps({"pages": talent_payloads}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return overview_path, store_path, talent_path, talent_pages


def _talent_page_metadata(payload: object) -> tuple[list[object], int | None]:
    if not isinstance(payload, dict):
        return [], None
    data = payload.get("data")
    if not isinstance(data, dict):
        return [], None
    rows = data.get("data")
    try:
        count = int(data["recordCount"]) if data.get("recordCount") is not None else None
    except (TypeError, ValueError):
        count = None
    return (rows if isinstance(rows, list) else []), count


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
        tables = ("store_daily_live_overviews", "store_daily_live_store_performance", "store_daily_live_talent_reports")
        day_sets = []
        for table in tables:
            rows = conn.execute(f"select {q(BUSINESS_DAY)} from {table} where {q(STORE_ID)}=? group by {q(BUSINESS_DAY)}", (store_id,)).fetchall()
            day_sets.append({date.fromisoformat(str(row[0])) for row in rows})
    finally:
        conn.close()
    return set.intersection(*day_sets) if day_sets else set()


def _log(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Live backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
