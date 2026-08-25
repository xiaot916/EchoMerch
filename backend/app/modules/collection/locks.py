from __future__ import annotations

from pathlib import Path

from app.core.local_database import LocalDatabase


def active_daily_batch(database_path: Path) -> str | None:
    """Return the running daily batch id, if one is occupying the browser."""
    database = LocalDatabase(database_path)
    database.initialize_schema()
    with database.connect() as conn:
        row = conn.execute(
            "select batch_id from collection_batches where status = 'running' "
            "order by datetime(started_at) desc limit 1"
        ).fetchone()
    return str(row[0]) if row else None


def active_feedback_run(database_path: Path) -> tuple[str, str] | None:
    """Return the active review/ask run that is occupying the browser."""
    database = LocalDatabase(database_path)
    database.initialize_schema()
    with database.connect() as conn:
        for table, label in (
            ("review_collection_runs", "评价"),
            ("ask_collection_runs", "问答"),
        ):
            if not conn.execute(
                "select 1 from sqlite_master where type = 'table' and name = ?",
                (table,),
            ).fetchone():
                continue
            row = conn.execute(
                f"select run_id from {table} where status in ('queued', 'running') "
                "order by datetime(started_at) desc limit 1"
            ).fetchone()
            if row:
                return label, str(row[0])
    return None
