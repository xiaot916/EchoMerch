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
from app.core.local_database import (  # noqa: E402
    BUSINESS_DAY,
    PROMOTION_CONTENT_TABLE,
    PROMOTION_ITEM_TABLE,
    STORE_ID,
    LocalDatabase,
    q,
)
from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_alimama_runtime_context,
)
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_alimama_rtb_report import (  # noqa: E402
    REPORT_CONFIG,
    alimama_report_home,
    fetch_alimama_report,
)


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "alimama_promotion_detail_backfill"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Alimama promotion item/content detail rows.")
    parser.add_argument("--detail-type", choices=("item", "content"), required=True)
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--csrf-id", default="")
    parser.add_argument("--login-point-id", default="")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--page-sleep", type=float, default=0.4)
    parser.add_argument("--day-sleep-min", type=float, default=1.2)
    parser.add_argument("--day-sleep-max", type=float, default=2.8)
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

    rpt_type = "item_promotion" if args.detail_type == "item" else "other_promotion"
    table = PROMOTION_ITEM_TABLE if args.detail_type == "item" else PROMOTION_CONTENT_TABLE
    days = _days(args.start, args.end)
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, table, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_{table}_{_stamp()}.jsonl"
    runtime = (
        resolve_alimama_runtime_context(
            source=args.session_source,
            cookie_env=args.cookie_env,
            csrf_id=args.csrf_id,
            login_point_id=args.login_point_id,
            browser_port=args.browser_port,
            report_home_url=alimama_report_home(rpt_type),
            timeout=args.timeout,
        )
        if pending
        else None
    )
    warehouse = WarehouseStore(args.database_path)
    runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(store_id=args.store_id, store_name=args.store_name, platform_store_id=args.platform_store_id)
    run_id = runs.create_run(store_id=args.store_id, task_type=f"alimama_{args.detail_type}_promotion", start_day=args.start, end_day=args.end, mode="refresh" if args.refresh_existing else "backfill", planned_days=len(days), log_file=log_path)
    summary: dict[str, Any] = {"run_id": run_id, "total": len(days), "inserted": 0, "skipped": 0, "failed": 0, "log_path": str(log_path)}
    failures = 0
    stopped = False
    try:
        for index, business_day in enumerate(days, start=1):
            if not args.refresh_existing and business_day in existing:
                summary["skipped"] += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=business_day, status="skipped_existing")
                print(f"[{index}/{len(days)}] {business_day.isoformat()} skipped existing")
                continue
            try:
                response_path, pages, source_rows = _fetch_day(business_day, args, rpt_type, runtime, args.output_dir)
                if args.detail_type == "item":
                    result = warehouse.ingest_alimama_promotion_item_report(source_path=response_path, business_day=business_day, store_name=args.store_name, platform_store_id=args.platform_store_id)
                else:
                    result = warehouse.ingest_alimama_promotion_content_report(source_path=response_path, business_day=business_day, store_name=args.store_name, platform_store_id=args.platform_store_id)
                summary["inserted"] += 1
                failures = 0
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=business_day, status="ingested", metric_count=result.metric_count)
                _log(log_path, {"day": business_day.isoformat(), "status": "ingested", "rows": source_rows, "pages": pages, "output": str(response_path)})
                print(f"[{index}/{len(days)}] {business_day.isoformat()} ingested {source_rows} rows ({pages} pages)")
            except Exception as exc:
                summary["failed"] += 1
                failures += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=business_day, status="ingest_failed", error_message=str(exc))
                _log(log_path, {"day": business_day.isoformat(), "status": "failed", "error": str(exc)})
                print(f"[{index}/{len(days)}] {business_day.isoformat()} failed: {exc}")
                if failures >= args.max_consecutive_failures:
                    stopped = True
                    break
                continue
            if index < len(days):
                time.sleep(random.uniform(args.day_sleep_min, args.day_sleep_max))
    finally:
        runs.finish_run(run_id=run_id, status="stopped" if stopped else "completed_with_errors" if summary["failed"] else "completed", success_days=summary["inserted"], skipped_days=summary["skipped"], failed_days=summary["failed"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _fetch_day(business_day: date, args: argparse.Namespace, rpt_type: str, runtime, output_dir: Path) -> tuple[Path, int, int]:
    day_dir = output_dir / args.detail_type / business_day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    config = REPORT_CONFIG[rpt_type]
    pages: list[dict[str, object]] = []
    rows_total = 0
    offset = 0
    for page_number in range(1, args.max_pages + 1):
        page_path = day_dir / f"page_{page_number:04d}_offset_{offset}.json"
        status, code, message, _ = fetch_alimama_report(start_day=business_day, end_day=business_day, output=page_path, cookie=runtime.session.cookie_header, csrf_id=runtime.csrf_id, login_point_id=runtime.login_point_id, rpt_type=rpt_type, query_fields=config["fields"], query_domains=config["domains"], biz_codes=config["biz_codes"], extra_body=config.get("extra_body"), offset=offset, page_size=args.page_size, timeout=args.timeout)
        if not 200 <= status < 300 or code != 0:
            raise RuntimeError(f"{rpt_type} page fetch failed: HTTP {status}, code {code}, message {message}")
        payload = json.loads(page_path.read_text(encoding="utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("list") if isinstance(data, dict) else None
        rows = rows if isinstance(rows, list) else []
        pages.append(payload)
        rows_total += len(rows)
        count = data.get("count") if isinstance(data, dict) else None
        if not rows or len(rows) < args.page_size or (count is not None and offset + len(rows) >= int(count)):
            break
        offset += len(rows)
        if args.page_sleep:
            time.sleep(args.page_sleep)
    else:
        raise RuntimeError(f"{rpt_type} pagination exceeded --max-pages")
    output = output_dir / f"{args.detail_type}_{business_day.isoformat()}.json"
    output.write_text(json.dumps({"pages": pages}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return output, len(pages), rows_total


def _existing_days(database: LocalDatabase, table: str, store_id: int) -> set[date]:
    conn = database.connect()
    try:
        rows = conn.execute(f"select {q(BUSINESS_DAY)} from {table} where {q(STORE_ID)}=? group by {q(BUSINESS_DAY)}", (store_id,)).fetchall()
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
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Alimama promotion detail backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
