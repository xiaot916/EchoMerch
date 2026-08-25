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
from app.warehouse.databank import ingest_snapshot  # noqa: E402
from scripts.fetch_databank_daily import fetch_databank_daily  # noqa: E402


DEFAULT_OUTPUT_DIR = Path(settings.local_database_path).parent / "raw_responses" / "databank_daily"
DEFAULT_BRAND_ID = "1917777264"
DEFAULT_BRAND_SUBJECT_ID = "1917777264"
DEFAULT_BRAND_NAME = "碧芭宝贝"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill the daily Tmall Brand Data Bank snapshot.")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--brand-id", default=DEFAULT_BRAND_ID)
    parser.add_argument("--brand-subject-id", default=DEFAULT_BRAND_SUBJECT_ID)
    parser.add_argument("--brand-name", default=DEFAULT_BRAND_NAME)
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
    existing: set[str] = set()
    with db.connect() as conn:
        existing = {str(row[0]) for row in conn.execute('select "业务日期" from brand_asset_daily_overviews where "品牌ID"=?', (args.brand_id,)).fetchall()}
    pending = [day for day in days if args.refresh_existing or day.isoformat() not in existing]
    runtime = resolve_databank_runtime_context(source=args.session_source, cookie_env=args.cookie_env, csrf_token="", browser_port=args.browser_port) if pending else None
    summary = {"total": len(days), "inserted": 0, "no_data": 0, "skipped": 0, "failed": 0}
    for day in days:
        if runtime is None or (not args.refresh_existing and day.isoformat() in existing):
            summary["skipped"] += 1
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
            if sum(counts.values()) == 0:
                summary["no_data"] += 1
                print(f"{day.isoformat()} no data")
            else:
                summary["inserted"] += 1
                print(f"{day.isoformat()} ingested {counts}")
        except Exception as exc:
            summary["failed"] += 1
            print(f"{day.isoformat()} failed: {exc}", file=sys.stderr)
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


if __name__ == "__main__":
    raise SystemExit(main())
