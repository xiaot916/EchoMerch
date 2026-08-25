from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import LocalDatabase  # noqa: E402
from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_utry_runtime_context,
)
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from scripts.fetch_utry_report import UTRY_REPORT_CONFIG, fetch_utry_report  # noqa: E402


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "utry_overviews"


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect U先 sample and repurchase daily reports.")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--refresh-existing", action="store_true")
    add_session_source_arguments(parser)
    args = parser.parse_args()
    if args.session_source != "drissionpage":
        raise ValueError("U先 requires --session-source drissionpage.")
    if args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")

    args.database_path = args.database_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    days = [args.start + timedelta(days=index) for index in range((args.end - args.start).days + 1)]
    database = LocalDatabase(args.database_path)
    database.initialize_schema()
    existing = _existing_days(database, args.store_id)
    pending = [day for day in days if args.refresh_existing or day not in existing]
    runtime = resolve_utry_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
        timeout=args.timeout,
    ) if pending else None

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_file = args.output_dir / f"backfill_utry_overviews_{args.start}_{args.end}.jsonl"
    runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
    )
    run_id = runs.create_run(
        store_id=args.store_id,
        task_type="utry_overviews",
        start_day=args.start,
        end_day=args.end,
        mode="refresh" if args.refresh_existing else "backfill",
        planned_days=len(days),
        log_file=log_file,
    )
    warehouse = WarehouseStore(args.database_path)
    summary = {"run_id": run_id, "total": len(days), "inserted": 0, "no_data": 0, "skipped": 0, "failed": 0}
    try:
        for day in days:
            if not args.refresh_existing and day in existing:
                summary["skipped"] += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="skipped_existing")
                continue
            try:
                if runtime is None:
                    raise RuntimeError("U先 runtime session is unavailable")
                counts: list[int] = []
                for report_type in ("sample", "repurchase"):
                    report_id = UTRY_REPORT_CONFIG[report_type]["report_id"]
                    template = runtime.templates.get(report_id)
                    if template is None:
                        raise RuntimeError(f"U先 report template not found: {report_type} ({report_id})")
                    output = args.output_dir / day.isoformat() / f"{report_type}.json"
                    status, code, message, _, rows, _ = fetch_utry_report(
                        template=template,
                        business_day=day,
                        output=output,
                        cookie=runtime.session.cookie_header,
                        timeout=args.timeout,
                    )
                    if not 200 <= status < 300 or code != 0:
                        raise RuntimeError(
                            f"U先 {report_type} fetch failed: HTTP {status}, code={code}, message={message or 'unknown'}"
                        )
                    if report_type == "sample":
                        result = warehouse.ingest_utry_sample_overview(
                            output, day, args.store_name, args.platform_store_id, http_status=status
                        )
                    else:
                        result = warehouse.ingest_utry_repurchase_overview(
                            output, day, args.store_name, args.platform_store_id, http_status=status
                        )
                    counts.append(rows)
                    _append_log(log_file, {"day": day.isoformat(), "report_type": report_type, "status": "ingested", "rows": rows, "metric_count": result.metric_count})
                if sum(counts) == 0:
                    summary["no_data"] += 1
                    runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="no_data", metric_count=0)
                    print(f"{day.isoformat()} no data")
                else:
                    summary["inserted"] += 1
                    runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingested", metric_count=sum(counts))
                    print(f"{day.isoformat()} ingested sample/repurchase ({counts})")
            except Exception as exc:
                summary["failed"] += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="ingest_failed", error_message=str(exc))
                _append_log(log_file, {"day": day.isoformat(), "status": "failed", "error": str(exc)})
                print(f"{day.isoformat()} failed: {exc}", file=sys.stderr)
    finally:
        runs.finish_run(
            run_id=run_id,
            status="completed_with_errors" if summary["failed"] else "completed",
            success_days=summary["inserted"],
            skipped_days=summary["skipped"],
            failed_days=summary["failed"],
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _existing_days(database: LocalDatabase, store_id: int) -> set[date]:
    with database.connect() as conn:
        rows = conn.execute(
            '''
            select sample."业务日期"
            from store_daily_utry_sample_overviews as sample
            inner join store_daily_utry_repurchase_overviews as repurchase
              on repurchase."店铺ID" = sample."店铺ID"
             and repurchase."业务日期" = sample."业务日期"
            where sample."店铺ID" = ?
            group by sample."业务日期"
            union
            select days."业务日期"
            from crawl_run_days as days
            inner join crawl_runs as runs
              on runs."采集任务ID" = days."采集任务ID"
            where days."店铺ID" = ?
              and runs."任务类型" = 'utry_overviews'
              and days."日期状态" = 'no_data'
            ''',
            (store_id, store_id),
        ).fetchall()
    return {date.fromisoformat(str(row[0])) for row in rows}


def _append_log(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"U先 backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
