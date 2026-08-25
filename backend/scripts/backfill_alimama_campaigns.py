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
from app.core.local_database import BUSINESS_DAY, PROMOTION_CAMPAIGN_TABLE, STORE_ID, LocalDatabase, q  # noqa: E402
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
DEFAULT_OUTPUT_DIR = (
    Path(settings.local_database_path).parent / "raw_responses" / "alimama_campaign_backfill"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill Alimama campaign-level metrics one business day at a time."
    )
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
    parser.add_argument("--empty-page-retries", type=int, default=2)
    parser.add_argument("--retry-sleep", type=float, default=1.0)
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
    if (
        args.page_sleep < 0
        or args.empty_page_retries < 0
        or args.retry_sleep < 0
        or args.day_sleep_min < 0
        or args.day_sleep_max < args.day_sleep_min
    ):
        raise ValueError("sleep values must be valid.")

    days = _days(args.start, args.end)
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"backfill_store_daily_promotion_campaigns_{_stamp()}.jsonl"
    runtime = (
        resolve_alimama_runtime_context(
            source=args.session_source,
            cookie_env=args.cookie_env,
            csrf_id=args.csrf_id,
            login_point_id=args.login_point_id,
            browser_port=args.browser_port,
            report_home_url=alimama_report_home("campaign"),
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
        task_type="alimama_campaigns",
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
            try:
                response_path, pages, source_rows = _fetch_day(
                    business_day,
                    args,
                    runtime.session.cookie_header if runtime else "",
                    runtime.csrf_id if runtime else "",
                    runtime.login_point_id if runtime else "",
                )
                result = warehouse.ingest_alimama_campaign_report(
                    source_path=response_path,
                    business_day=business_day,
                    store_name=args.store_name,
                    platform_store_id=args.platform_store_id,
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
                        "campaign_rows": source_rows,
                        "source_rows": source_rows,
                        "pages": pages,
                        "output": str(response_path),
                    },
                )
                print(
                    f"[{index}/{len(days)}] {business_day.isoformat()} ingested "
                    f"{source_rows} campaign rows ({pages} pages)"
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
                time.sleep(random.uniform(args.day_sleep_min, args.day_sleep_max))
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


def _fetch_day(
    business_day: date,
    args: argparse.Namespace,
    cookie: str,
    csrf_id: str,
    login_point_id: str,
) -> tuple[Path, int, int]:
    day_dir = args.output_dir / business_day.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    pages: list[dict[str, object]] = []
    source_rows = 0
    offset = 0
    config = REPORT_CONFIG["campaign"]
    request_biz_codes = config["biz_codes"]
    for page_number in range(1, args.max_pages + 1):
        page_path = day_dir / f"page_{page_number:04d}_offset_{offset}.json"
        payload, rows, count = _fetch_page(
            business_day=business_day,
            page_path=page_path,
            args=args,
            cookie=cookie,
            csrf_id=csrf_id,
            login_point_id=login_point_id,
            config=config,
            biz_codes=request_biz_codes,
            offset=offset,
        )
        if page_number == 1 and not rows:
            for retry_number in range(1, args.empty_page_retries + 1):
                if args.retry_sleep:
                    time.sleep(args.retry_sleep)
                payload, rows, count = _fetch_page(
                    business_day=business_day,
                    page_path=page_path,
                    args=args,
                    cookie=cookie,
                    csrf_id=csrf_id,
                    login_point_id=login_point_id,
                    config=config,
                    biz_codes=request_biz_codes,
                    offset=offset,
                )
                if rows:
                    break
                print(
                    f"{business_day.isoformat()} empty campaign response "
                    f"retry {retry_number}/{args.empty_page_retries}"
                )
        fallback_biz_codes = config.get("fallback_biz_codes")
        if page_number == 1 and not rows and fallback_biz_codes:
            request_biz_codes = fallback_biz_codes
            payload, rows, count = _fetch_page(
                business_day=business_day,
                page_path=page_path,
                args=args,
                cookie=cookie,
                csrf_id=csrf_id,
                login_point_id=login_point_id,
                config=config,
                biz_codes=request_biz_codes,
                offset=offset,
            )
        pages.append(payload)
        source_rows += len(rows)
        if not rows or len(rows) < args.page_size or (count is not None and offset + len(rows) >= count):
            break
        offset += len(rows)
        if args.page_sleep:
            time.sleep(args.page_sleep)
    else:
        raise RuntimeError("campaign pagination exceeded --max-pages")

    output = args.output_dir / f"campaign_{business_day.isoformat()}.json"
    output.write_text(
        json.dumps({"pages": pages}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return output, len(pages), source_rows


def _fetch_page(
    *,
    business_day: date,
    page_path: Path,
    args: argparse.Namespace,
    cookie: str,
    csrf_id: str,
    login_point_id: str,
    config: dict[str, object],
    biz_codes: tuple[str, ...] | None,
    offset: int,
) -> tuple[dict[str, object], list[object], int | None]:
    status, code, message, _ = fetch_alimama_report(
        start_day=business_day,
        end_day=business_day,
        output=page_path,
        cookie=cookie,
        csrf_id=csrf_id,
        login_point_id=login_point_id,
        rpt_type="campaign",
        query_fields=config["fields"],
        query_domains=config["domains"],
        biz_codes=biz_codes,
        by_page_without_count=bool(config.get("by_page_without_count", False)),
        extra_body=config.get("extra_body"),
        offset=offset,
        page_size=args.page_size,
        timeout=args.timeout,
    )
    if not 200 <= status < 300 or code != 0:
        raise RuntimeError(
            f"campaign page fetch failed: HTTP {status}, code {code}, message {message}"
        )
    payload = json.loads(page_path.read_text(encoding="utf-8"))
    rows, count = _page_rows(payload)
    return payload, rows, count


def _page_rows(payload: object) -> tuple[list[object], int | None]:
    if not isinstance(payload, dict):
        return [], None
    data = payload.get("data")
    if not isinstance(data, dict):
        return [], None
    rows = data.get("list")
    try:
        count = int(data["count"]) if data.get("count") is not None else None
    except (TypeError, ValueError):
        count = None
    return (rows if isinstance(rows, list) else []), count


def _existing_days(database: LocalDatabase, store_id: int) -> set[date]:
    conn = database.connect()
    try:
        rows = conn.execute(
            f"select {q(BUSINESS_DAY)} from {PROMOTION_CAMPAIGN_TABLE} "
            f"where {q(STORE_ID)}=? group by {q(BUSINESS_DAY)}",
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
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Alimama campaign backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
