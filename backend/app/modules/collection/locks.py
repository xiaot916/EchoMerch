from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.local_database import LocalDatabase


_FEEDBACK_IDLE_TIMEOUT = timedelta(minutes=10)
_FEEDBACK_PROGRESS_TIMEOUT = timedelta(minutes=45)
_STALE_FEEDBACK_ERROR = "采集任务长时间没有进展，已自动释放任务锁，请重新发起。"


def active_daily_batch(database_path: Path) -> str | None:
    """Return the running daily batch id, if one is occupying the browser."""
    database = LocalDatabase(database_path)
    with database.connect() as conn:
        row = conn.execute(
            "select batch_id from collection_batches where status = 'running' "
            "order by datetime(started_at) desc limit 1"
        ).fetchone()
    return str(row[0]) if row else None


def active_feedback_run(database_path: Path) -> tuple[str, str] | None:
    """Return the active review/ask run that is occupying the browser."""
    database = LocalDatabase(database_path)
    with database.connect(read_only=False) as conn:
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
                f"select * from {table} where status in ('queued', 'running') "
                "order by datetime(started_at) desc limit 1"
            ).fetchone()
            if row:
                if _reclaim_stale_feedback_run(conn, table, row):
                    conn.commit()
                    continue
                return label, str(row[0])
    return None


def _reclaim_stale_feedback_run(conn, table: str, row: object) -> bool:
    """Release a background feedback task that can no longer be progressing.

    Review tables created by older versions only have four columns, so those
    rows remain protected. Current tables expose page/fetch counters, allowing
    us to distinguish a hung preflight from a legitimately long collection.
    """

    keys = set(row.keys()) if hasattr(row, "keys") else set()
    if "pages" not in keys or "fetched_count" not in keys:
        return False
    started_at = _parse_timestamp(row["started_at"])
    if started_at is None:
        return False
    pages = _as_nonnegative_int(row["pages"])
    fetched = _as_nonnegative_int(row["fetched_count"])
    timeout = _FEEDBACK_IDLE_TIMEOUT if pages == 0 and fetched == 0 else _FEEDBACK_PROGRESS_TIMEOUT
    if datetime.now(timezone.utc) - started_at < timeout:
        return False
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        f"update {table} set status = 'failed', finished_at = ?, error = coalesce(error, ?) "
        "where run_id = ? and status in ('queued', 'running')",
        (finished_at, _STALE_FEEDBACK_ERROR, row["run_id"]),
    )
    return True


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _as_nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
