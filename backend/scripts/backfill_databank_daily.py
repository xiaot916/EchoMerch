from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import LocalDatabase  # noqa: E402
from app.integrations.tmall_session import add_session_source_arguments, resolve_databank_runtime_context  # noqa: E402
from app.modules.imports.crawl_run_store import CrawlRunStore  # noqa: E402
from app.warehouse.databank import ingest_snapshot  # noqa: E402
from scripts.fetch_databank_daily import fetch_databank_daily  # noqa: E402


DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "databank_daily"
DEFAULT_BRAND_ID = "1917777264"
DEFAULT_BRAND_SUBJECT_ID = "1917777264"
DEFAULT_BRAND_NAME = "碧芭宝贝"
DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill the daily Tmall Brand Data Bank snapshot.")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--brand-id", default=DEFAULT_BRAND_ID)
    parser.add_argument("--brand-subject-id", default=DEFAULT_BRAND_SUBJECT_ID)
    parser.add_argument("--brand-name", default=DEFAULT_BRAND_NAME)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument(
        "--prune-before",
        type=date.fromisoformat,
        help="Delete existing brand daily facts before this date after the requested backfill succeeds.",
    )
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    if args.cookie_env == "SYCM_COOKIE":
        args.cookie_env = "DATABANK_COOKIE"
    if args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    args.database_path = args.database_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    days = [args.start + timedelta(days=i) for i in range((args.end - args.start).days + 1)]
    db = LocalDatabase(args.database_path)
    db.initialize_schema()
    with db.connect(read_only=False) as conn:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        conn.execute(
            'insert into brands ("品牌ID", "品牌主体ID", "品牌名称", "品牌状态", "创建时间", "更新时间") values (?, ?, ?, ?, ?, ?) on conflict("品牌ID") do update set "品牌主体ID"=excluded."品牌主体ID", "品牌名称"=excluded."品牌名称", "更新时间"=excluded."更新时间"',
            (args.brand_id, args.brand_subject_id, args.brand_name, "active", now, now),
        )
    existing = _existing_days(db, brand_id=args.brand_id, store_id=args.store_id)
    pending = [day for day in days if args.refresh_existing or day.isoformat() not in existing]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_file = args.output_dir / f"backfill_databank_daily_{args.start}_{args.end}.jsonl"
    runs = CrawlRunStore(args.database_path)
    runs.ensure_store_reference(
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
    )
    run_id = runs.create_run(
        store_id=args.store_id,
        task_type="databank_daily",
        start_day=args.start,
        end_day=args.end,
        mode="refresh" if args.refresh_existing else "backfill",
        planned_days=len(days),
        log_file=log_file,
    )
    runtime = None
    summary = {"run_id": run_id, "total": len(days), "inserted": 0, "no_data": 0, "skipped": 0, "failed": 0}
    recorded_days: set[date] = set()
    try:
        if pending:
            runtime = resolve_databank_runtime_context(
                source=args.session_source,
                cookie_env=args.cookie_env,
                csrf_token="",
                browser_port=args.browser_port,
            )
        for day in days:
            if runtime is None or (not args.refresh_existing and day.isoformat() in existing):
                summary["skipped"] += 1
                runs.record_day(run_id=run_id, store_id=args.store_id, business_day=day, status="skipped_existing")
                recorded_days.add(day)
                _append_log(log_file, {"day": day.isoformat(), "status": "skipped_existing"})
                continue
            output = args.output_dir / f"{day.isoformat()}.json"
            try:
                status, _ = fetch_databank_daily(
                    business_day=day,
                    output=output,
                    cookie=runtime.session.cookie_header,
                    csrf_token=runtime.csrf_token,
                    timeout=args.timeout,
                    brand_id=args.brand_id,
                )
                if not 200 <= status < 300:
                    raise RuntimeError(f"fetch failed: HTTP {status}")
                payload = json.loads(output.read_text(encoding="utf-8"))
                counts = ingest_snapshot(
                    args.database_path,
                    brand_id=args.brand_id,
                    business_day=day,
                    payload={k: v.get("data", v) if isinstance(v, dict) else v for k, v in payload.items()},
                )
                metric_count = sum(counts.values())
                if metric_count == 0:
                    summary["no_data"] += 1
                    day_status = "no_data"
                    print(f"{day.isoformat()} no data")
                else:
                    summary["inserted"] += 1
                    day_status = "ingested"
                    print(f"{day.isoformat()} ingested {counts}")
                runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status=day_status,
                    metric_count=metric_count,
                )
                recorded_days.add(day)
                _append_log(log_file, {"day": day.isoformat(), "status": day_status, "metric_count": metric_count, "counts": counts, "output": str(output)})
            except Exception as exc:
                summary["failed"] += 1
                runs.record_day(
                    run_id=run_id,
                    store_id=args.store_id,
                    business_day=day,
                    status="ingest_failed",
                    error_message=str(exc),
                )
                recorded_days.add(day)
                _append_log(log_file, {"day": day.isoformat(), "status": "failed", "error": str(exc), "output": str(output)})
                print(f"{day.isoformat()} failed: {exc}", file=sys.stderr)
    except Exception as exc:
        unrecorded_days = [day for day in pending if day not in recorded_days]
        for day in unrecorded_days:
            runs.record_day(
                run_id=run_id,
                store_id=args.store_id,
                business_day=day,
                status="ingest_failed",
                error_message=str(exc),
            )
            _append_log(log_file, {"day": day.isoformat(), "status": "failed", "error": str(exc)})
        summary["failed"] += len(unrecorded_days)
        print(f"品牌数据银行运行失败: {exc}", file=sys.stderr)
    finally:
        runs.finish_run(
            run_id=run_id,
            status="completed_with_errors" if summary["failed"] else "completed",
            success_days=summary["inserted"],
            skipped_days=summary["skipped"],
            failed_days=summary["failed"],
        )
    if args.prune_before and summary["failed"] == 0:
        with db.connect(read_only=False) as conn:
            for table in (
                "brand_asset_daily_overviews",
                "brand_asset_daily_stages",
                "brand_asset_daily_dimensions",
                "brand_asset_daily_metrics",
            ):
                if LocalDatabase._table_exists(conn, table):
                    conn.execute(
                        f'delete from "{table}" where "品牌ID"=? and "业务日期"<?',
                        (args.brand_id, args.prune_before.isoformat()),
                    )
        print(f"pruned brand {args.brand_id} facts before {args.prune_before.isoformat()}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def _existing_days(database: LocalDatabase, *, brand_id: str, store_id: int) -> set[str]:
    """Return only fully persisted brand days plus explicit no-data runs."""

    tables = (
        "brand_asset_daily_overviews",
        "brand_asset_daily_stages",
        "brand_asset_daily_dimensions",
        "brand_asset_daily_metrics",
    )
    with database.connect() as conn:
        completed = {
            str(row[0])
            for row in conn.execute(
                f'''select overview."业务日期"
                    from {tables[0]} as overview
                    inner join {tables[1]} as stages
                      on stages."品牌ID" = overview."品牌ID"
                     and stages."业务日期" = overview."业务日期"
                    inner join {tables[2]} as dimensions
                      on dimensions."品牌ID" = overview."品牌ID"
                     and dimensions."业务日期" = overview."业务日期"
                    inner join {tables[3]} as metrics
                      on metrics."品牌ID" = overview."品牌ID"
                     and metrics."业务日期" = overview."业务日期"
                    where overview."品牌ID" = ?
                    group by overview."业务日期"''',
                (brand_id,),
            ).fetchall()
        }
        no_data = {
            str(row[0])
            for row in conn.execute(
                '''select days."业务日期"
                   from crawl_run_days as days
                   inner join crawl_runs as runs
                     on runs."采集任务ID" = days."采集任务ID"
                   where days."店铺ID" = ?
                     and runs."任务类型" = 'databank_daily'
                     and days."日期状态" = 'no_data' ''',
                (store_id,),
            ).fetchall()
        }
    return completed | no_data


def _append_log(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
