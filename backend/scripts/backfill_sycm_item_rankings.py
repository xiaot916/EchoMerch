from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

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
from app.warehouse.sycm_item_ranking import parse_payload  # noqa: E402
from scripts.fetch_sycm_item_ranking import fetch_item_ranking  # noqa: E402


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "sycm_item_rankings_backfill"
SERVER_PAGE_SIZE = 20


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill SYCM product rankings day by day.")
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--token", default="")
    parser.add_argument("--page-size", type=int, default=SERVER_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--page-sleep", type=float, default=0.35)
    parser.add_argument("--day-sleep-min", type=float, default=1.2)
    parser.add_argument("--day-sleep-max", type=float, default=2.8)
    parser.add_argument("--qps-retries", type=int, default=3)
    parser.add_argument("--qps-backoff-seconds", type=float, default=3.0)
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
    if (
        args.page_sleep < 0
        or args.day_sleep_min < 0
        or args.day_sleep_max < args.day_sleep_min
        or args.qps_retries < 0
        or args.qps_backoff_seconds < 0
    ):
        raise ValueError("sleep values must be valid.")

    days = _days(args.start, args.end)
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_store_daily_product_rankings_{_stamp()}.jsonl"
    session = (
        resolve_runtime_session(source=args.session_source, cookie_env=args.cookie_env, browser_port=args.browser_port)
        if pending else None
    )
    warehouse = WarehouseStore(args.database_path)
    runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
    )
    run_id = runs.create_run(store_id=args.store_id, task_type="sycm_item_rankings", start_day=args.start, end_day=args.end, mode="refresh" if args.refresh_existing else "backfill", planned_days=len(days), log_file=log_path)
    summary = {"run_id": run_id, "total": len(days), "inserted": 0, "skipped": 0, "failed": 0, "log_path": str(log_path)}
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
                combined, row_count, pages, stop_reason = _fetch_day(day, args, session.cookie_header if session else "")
                result = warehouse.ingest_sycm_item_ranking(source_path=combined, business_day=day, store_name=args.store_name, platform_store_id=args.platform_store_id)
                summary["inserted"] += 1
                failures = 0
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingested", metric_count=result.row_count)
                _log(log_path, {"day": day.isoformat(), "status": "ingested", "rows": row_count, "pages": pages, "stop_reason": stop_reason, "output": str(combined)})
                print(f"[{index}/{len(days)}] {day.isoformat()} ingested {result.row_count} rows ({pages} pages, {stop_reason})")
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


def _fetch_day(day: date, args: argparse.Namespace, cookie: str) -> tuple[Path, int, int, str]:
    day_dir = args.output_dir / day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    payloads: list[dict[str, object]] = []
    rows = 0
    stop_reason = "max_pages"
    for page in range(1, args.max_pages + 1):
        output = day_dir / f"page_{page:04d}.json"
        status, code, message, _ = _fetch_page_with_qps_retry(
            day=day,
            args=args,
            cookie=cookie,
            page=page,
            output=output,
        )
        if not 200 <= status < 300 or code != 0:
            raise RuntimeError(f"page {page} fetch failed: HTTP {status}, code {code}, message {message}")
        payload = json.loads(output.read_text(encoding="utf-8"))
        source_rows, record_count = _source_page_metadata(payload)
        parsed = parse_payload(payload, business_day=day)
        payloads.append(payload)
        rows += len(parsed.rows)
        if parsed.reached_zero_payment_items:
            stop_reason = "zero_payment_items"
            break
        if not source_rows:
            stop_reason = "no_more_rows"
            break
        if record_count is not None and page * len(source_rows) >= record_count:
            stop_reason = "record_count_reached"
            break
        if len(source_rows) < SERVER_PAGE_SIZE:
            stop_reason = "short_page"
            break
        if args.page_sleep:
            time.sleep(args.page_sleep)
    combined = args.output_dir / f"item_ranking_{day.isoformat()}.json"
    combined.write_text(json.dumps({"pages": payloads}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return combined, rows, len(payloads), stop_reason


def _fetch_page_with_qps_retry(
    *,
    day: date,
    args: argparse.Namespace,
    cookie: str,
    page: int,
    output: Path,
) -> tuple[int, int | None, str | None, int]:
    """Retry only the platform's explicit QPS response with bounded backoff."""

    for attempt in range(args.qps_retries + 1):
        result = fetch_item_ranking(
            day=day,
            output=output,
            cookie=cookie,
            token=args.token,
            page=page,
            page_size=args.page_size,
            timeout=args.timeout,
        )
        _status, code, _message, _size = result
        if code != 1800 or attempt == args.qps_retries:
            return result
        delay = args.qps_backoff_seconds * (2 ** attempt) + random.uniform(0, 0.75)
        print(
            f"{day.isoformat()} page {page} QPS limited; retrying in {delay:.1f}s "
            f"({attempt + 1}/{args.qps_retries})"
        )
        time.sleep(delay)
    raise AssertionError("unreachable")


def _source_page_metadata(payload: object) -> tuple[list[object], int | None]:
    if not isinstance(payload, dict):
        return [], None
    data = payload.get("data")
    if not isinstance(data, dict):
        return [], None
    rows = data.get("data")
    record_count = data.get("recordCount")
    try:
        normalized_count = int(record_count) if record_count is not None else None
    except (TypeError, ValueError):
        normalized_count = None
    return (rows if isinstance(rows, list) else []), normalized_count


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
        rows = conn.execute(f"select {q(BUSINESS_DAY)} from store_daily_product_rankings where {q(STORE_ID)}=? group by {q(BUSINESS_DAY)}", (store_id,)).fetchall()
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
        print(f"Item-ranking backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
