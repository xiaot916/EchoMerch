from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.captures.analyzer import ParsedCapture


SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_dir TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    analyzed_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS capture_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL UNIQUE,
    capture_at TEXT NOT NULL,
    capture_date TEXT NOT NULL,
    session_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    kind TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    is_binary INTEGER NOT NULL,
    is_json_like INTEGER NOT NULL,
    sensitive_field_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS endpoint_observations (
    capture_file_id INTEGER NOT NULL REFERENCES capture_files(id) ON DELETE CASCADE,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    family TEXT NOT NULL,
    confidence TEXT NOT NULL,
    PRIMARY KEY (capture_file_id, host, path, family)
);

CREATE TABLE IF NOT EXISTS field_observations (
    capture_file_id INTEGER NOT NULL REFERENCES capture_files(id) ON DELETE CASCADE,
    direction TEXT NOT NULL,
    field_path TEXT NOT NULL,
    value_kind TEXT NOT NULL,
    PRIMARY KEY (capture_file_id, direction, field_path, value_kind)
);

CREATE TABLE IF NOT EXISTS shape_observations (
    capture_file_id INTEGER NOT NULL REFERENCES capture_files(id) ON DELETE CASCADE,
    field_path TEXT NOT NULL,
    value_kind TEXT NOT NULL,
    PRIMARY KEY (capture_file_id, field_path, value_kind)
);

CREATE TABLE IF NOT EXISTS daily_request_candidates (
    capture_file_id INTEGER NOT NULL REFERENCES capture_files(id) ON DELETE CASCADE,
    business_date TEXT,
    date_mode TEXT NOT NULL,
    params_json TEXT NOT NULL,
    PRIMARY KEY (capture_file_id)
);

CREATE INDEX IF NOT EXISTS idx_capture_files_date
    ON capture_files(capture_date);
CREATE INDEX IF NOT EXISTS idx_endpoint_family
    ON endpoint_observations(family);
CREATE INDEX IF NOT EXISTS idx_field_path
    ON field_observations(field_path);
CREATE INDEX IF NOT EXISTS idx_daily_request_business_date
    ON daily_request_candidates(business_date);
"""


class CaptureStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_capture(
        self,
        capture: "ParsedCapture",
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is not None:
            self._upsert_capture(connection, capture)
            return
        with self._connect() as owned_connection:
            self._upsert_capture(owned_connection, capture)

    def _upsert_capture(
        self,
        connection: sqlite3.Connection,
        capture: "ParsedCapture",
    ) -> None:
        imported_at = datetime.now().astimezone().isoformat()
        direction = "request" if "req" in capture.kind else "response"
        connection.execute(
            """
            INSERT INTO capture_files (
                source_name, capture_at, capture_date, session_id, sequence_no,
                kind, size_bytes, sha256, is_binary, is_json_like,
                sensitive_field_count, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                capture_at=excluded.capture_at,
                capture_date=excluded.capture_date,
                session_id=excluded.session_id,
                sequence_no=excluded.sequence_no,
                kind=excluded.kind,
                size_bytes=excluded.size_bytes,
                sha256=excluded.sha256,
                is_binary=excluded.is_binary,
                is_json_like=excluded.is_json_like,
                sensitive_field_count=excluded.sensitive_field_count,
                imported_at=excluded.imported_at
            """,
            (
                capture.source_name,
                capture.capture_at.isoformat(),
                capture.capture_at.date().isoformat(),
                capture.session_id,
                capture.sequence,
                capture.kind,
                capture.size_bytes,
                capture.sha256,
                int(capture.is_binary),
                int(capture.is_json_like),
                capture.sensitive_field_count,
                imported_at,
            ),
        )
        row = connection.execute(
            "SELECT id FROM capture_files WHERE source_name = ?",
            (capture.source_name,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to store capture {capture.source_name}")
        capture_id = int(row["id"])
        connection.execute(
            "DELETE FROM endpoint_observations WHERE capture_file_id = ?",
            (capture_id,),
        )
        connection.execute(
            "DELETE FROM field_observations WHERE capture_file_id = ?",
            (capture_id,),
        )
        connection.execute(
            "DELETE FROM shape_observations WHERE capture_file_id = ?",
            (capture_id,),
        )
        connection.execute(
            "DELETE FROM daily_request_candidates WHERE capture_file_id = ?",
            (capture_id,),
        )
        connection.executemany(
            """
            INSERT INTO endpoint_observations
                (capture_file_id, host, path, family, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    capture_id,
                    endpoint["host"],
                    endpoint["path"],
                    endpoint["family"],
                    endpoint["confidence"],
                )
                for endpoint in capture.endpoints
            ],
        )
        connection.executemany(
            """
            INSERT INTO field_observations
                (capture_file_id, direction, field_path, value_kind)
            VALUES (?, ?, ?, ?)
            """,
            [
                (capture_id, direction, field["path"], field["kind"])
                for field in capture.fields
            ],
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO shape_observations
                (capture_file_id, field_path, value_kind)
            VALUES (?, ?, ?)
            """,
            [(capture_id, row["path"], row["kind"]) for row in capture.shape],
        )
        if capture.daily_candidate:
            connection.execute(
                """
                INSERT OR REPLACE INTO daily_request_candidates
                    (capture_file_id, business_date, date_mode, params_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    capture_id,
                    capture.daily_candidate.get("business_date"),
                    capture.daily_candidate["date_mode"],
                    capture.daily_candidate["params_json"],
                ),
            )

    def record_run(
        self,
        *,
        capture_dir: str,
        since: date | None,
        until: date | None,
        started_at: datetime,
        finished_at: datetime,
        file_count: int,
        analyzed_count: int,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO analysis_runs (
                    capture_dir, window_start, window_end, started_at, finished_at,
                    file_count, analyzed_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capture_dir,
                    since.isoformat() if since else None,
                    until.isoformat() if until else None,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    file_count,
                    analyzed_count,
                ),
            )
            return int(cursor.lastrowid)

    def summary(self, *, since: date | None = None, until: date | None = None) -> dict[str, Any]:
        predicates: list[str] = []
        params: list[str] = []
        if since:
            predicates.append("capture_date >= ?")
            params.append(since.isoformat())
        if until:
            predicates.append("capture_date <= ?")
            params.append(until.isoformat())
        where = f"WHERE {' AND '.join(predicates)}" if predicates else ""

        with self._connect() as connection:
            daily = connection.execute(
                f"""
                SELECT capture_date, COUNT(*) AS file_count, SUM(size_bytes) AS bytes
                FROM capture_files
                {where}
                GROUP BY capture_date
                ORDER BY capture_date
                """,
                params,
            ).fetchall()
            families = connection.execute(
                f"""
                SELECT family, COUNT(*) AS observations
                FROM endpoint_observations
                WHERE capture_file_id IN (
                    SELECT id FROM capture_files {where}
                )
                GROUP BY family
                ORDER BY observations DESC, family
                """,
                params,
            ).fetchall()
            endpoints = connection.execute(
                f"""
                SELECT e.family, e.host, e.path, COUNT(DISTINCT e.capture_file_id) AS files
                FROM endpoint_observations e
                JOIN capture_files c ON c.id = e.capture_file_id
                {where.replace("capture_date", "c.capture_date")}
                GROUP BY e.family, e.host, e.path
                ORDER BY files DESC, e.family, e.path
                """,
                params,
            ).fetchall()
            fields = connection.execute(
                f"""
                SELECT f.direction, f.field_path, f.value_kind,
                       COUNT(DISTINCT f.capture_file_id) AS files
                FROM field_observations f
                JOIN capture_files c ON c.id = f.capture_file_id
                {where.replace("capture_date", "c.capture_date")}
                GROUP BY f.direction, f.field_path, f.value_kind
                ORDER BY files DESC, f.direction, f.field_path
                """,
                params,
            ).fetchall()
            daily_requests = connection.execute(
                f"""
                SELECT d.business_date, d.date_mode, COUNT(*) AS files
                FROM daily_request_candidates d
                JOIN capture_files c ON c.id = d.capture_file_id
                {where.replace("capture_date", "c.capture_date")}
                GROUP BY d.business_date, d.date_mode
                ORDER BY files DESC, d.business_date
                """,
                params,
            ).fetchall()
            latest_run = connection.execute(
                "SELECT finished_at FROM analysis_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()

        return {
            "window_start": since.isoformat() if since else None,
            "window_end": until.isoformat() if until else None,
            "generated_at": datetime.now().astimezone().isoformat(),
            "daily": [dict(row) for row in daily],
            "families": [dict(row) for row in families],
            "endpoints": [dict(row) for row in endpoints],
            "fields": [dict(row) for row in fields],
            "daily_requests": [dict(row) for row in daily_requests],
            "last_run_at": latest_run["finished_at"] if latest_run else None,
        }

    def api_summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS file_count,
                    MIN(capture_date) AS first_date,
                    MAX(capture_date) AS last_date,
                    MAX(imported_at) AS imported_at
                FROM capture_files
                """
            ).fetchone()
            family_rows = connection.execute(
                """
                SELECT family, COUNT(*) AS observations
                FROM endpoint_observations
                GROUP BY family
                ORDER BY observations DESC, family
                """
            ).fetchall()
            daily_rows = connection.execute(
                """
                SELECT business_date, date_mode, COUNT(*) AS files
                FROM daily_request_candidates
                GROUP BY business_date, date_mode
                ORDER BY files DESC, business_date
                """
            ).fetchall()
        return {
            "file_count": int(row["file_count"] or 0),
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "imported_at": row["imported_at"],
            "families": [dict(item) for item in family_rows],
            "daily_requests": [dict(item) for item in daily_rows],
        }
