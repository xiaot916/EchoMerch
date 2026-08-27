from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.modules.collection.locks import active_feedback_run
from app.modules.reviews.service import ReviewService


def _insert_run(database_path: Path, table: str, started_at: str, *, pages: int, fetched: int) -> None:
    ReviewService(database_path)
    database = LocalDatabase(database_path)
    with database.connect(initialize=True) as conn:
        conn.execute(
            f"insert into {table} (run_id, mode, status, started_at, pages, fetched_count) "
            "values (?, 'incremental', 'running', ?, ?, ?)",
            (f"{table}-run", started_at, pages, fetched),
        )
        conn.commit()


def test_active_feedback_run_reclaims_stalled_preflight(tmp_path: Path) -> None:
    database_path = tmp_path / "locks.sqlite3"
    started_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    _insert_run(database_path, "review_collection_runs", started_at, pages=0, fetched=0)

    assert active_feedback_run(database_path) is None

    with sqlite3.connect(database_path) as conn:
        row = conn.execute(
            "select status, error from review_collection_runs where run_id = ?",
            ("review_collection_runs-run",),
        ).fetchone()
    assert row == ("failed", "采集任务长时间没有进展，已自动释放任务锁，请重新发起。")


def test_active_feedback_run_keeps_recent_task_locked(tmp_path: Path) -> None:
    database_path = tmp_path / "locks.sqlite3"
    started_at = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    _insert_run(database_path, "review_collection_runs", started_at, pages=2, fetched=40)

    assert active_feedback_run(database_path) == ("评价", "review_collection_runs-run")
