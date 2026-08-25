from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import (  # noqa: E402
    BUSINESS_DAY,
    DAILY_FACT_TABLE_SORT_COLUMNS,
    STORE_ID,
    LocalDatabase,
    q,
)


def _backup_database(source_path: Path, backup_path: Path) -> None:
    """Create a consistent SQLite snapshot, including committed WAL content."""
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True, timeout=30)
    destination = sqlite3.connect(backup_path, timeout=30)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _existing_tables(database_path: Path, requested_tables: tuple[str, ...]) -> dict[str, int]:
    with sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True, timeout=30) as conn:
        existing = {
            str(row[0])
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }
        return {
            table: int(conn.execute(f"select count(*) from {q(table)}").fetchone()[0])
            for table in requested_tables
            if table in existing
        }


def _physical_order_breaks(database_path: Path, tables: tuple[str, ...]) -> dict[str, int]:
    breaks: dict[str, int] = {}
    with sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True, timeout=30) as conn:
        for table in tables:
            previous: tuple[object, object] | None = None
            table_breaks = 0
            rows = conn.execute(
                f"select {q(STORE_ID)}, {q(BUSINESS_DAY)} from {q(table)} order by rowid"
            )
            for store_id, business_day in rows:
                current = (store_id, business_day)
                if previous is not None and current < previous:
                    table_breaks += 1
                previous = current
            if table_breaks:
                breaks[table] = table_breaks
    return breaks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Physically reorder known daily fact tables by store and business day."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path(settings.local_database_path),
    )
    parser.add_argument(
        "--table",
        dest="tables",
        action="append",
        choices=sorted(DAILY_FACT_TABLE_SORT_COLUMNS),
        help="Recluster only this table. Repeat the option for several tables.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(settings.local_database_path).parent / "backups",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report affected tables without changing the database.",
    )
    args = parser.parse_args()
    database_path = args.database_path.expanduser().resolve()
    backup_dir = args.backup_dir.expanduser().resolve()
    requested_tables = tuple(args.tables or DAILY_FACT_TABLE_SORT_COLUMNS)

    if not database_path.exists():
        raise FileNotFoundError(f"Local database does not exist: {database_path}")

    existing_rows = _existing_tables(database_path, requested_tables)
    summary: dict[str, Any] = {
        "database": str(database_path),
        "tables": existing_rows,
        "dry_run": args.dry_run,
    }
    if args.dry_run:
        summary["physical_order_breaks"] = _physical_order_breaks(
            database_path,
            tuple(existing_rows),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{database_path.stem}_before_recluster_{stamp}.sqlite3"
    _backup_database(database_path, backup_path)

    rows = LocalDatabase(database_path).recluster_daily_fact_tables(requested_tables)
    with sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True, timeout=30) as conn:
        integrity_check = str(conn.execute("pragma integrity_check").fetchone()[0])

    summary.update(
        {
            "backup": str(backup_path),
            "tables": rows,
            "integrity_check": integrity_check,
            "physical_order_breaks": _physical_order_breaks(
                database_path,
                tuple(rows),
            ),
        }
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if integrity_check == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
