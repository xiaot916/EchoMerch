from __future__ import annotations

import sqlite3
from datetime import date, datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.local_database import (
    BUSINESS_DAY,
    CRAWL_RUN_ID,
    CRAWL_TASK_TYPE,
    DAY_STATUS,
    END_DAY,
    ERROR_MESSAGE,
    FINISHED_AT,
    ITEM_DAY_ID,
    LOG_FILE,
    METRIC_COUNT,
    PLATFORM_CODE,
    PLATFORM_ID,
    PLATFORM_NAME,
    PLANNED_DAYS,
    RUN_MODE,
    RUN_STATUS,
    SKIPPED_DAYS,
    START_DAY,
    STARTED_AT,
    STORE_ID,
    STORE_NAME,
    STORE_SUBJECT_ID,
    STATUS,
    CREATED_AT,
    FIRST_SEEN_AT,
    UPDATED_AT,
    FAILED_DAYS,
    SUCCESS_DAYS,
    LocalDatabase,
    q,
)
from app.modules.imports.schemas import (
    CrawlRun,
    CrawlRunDay,
    CrawlRunDetail,
    CrawlRunList,
)


class CrawlRunMissing(RuntimeError):
    pass


class CrawlRunAlreadyRunning(RuntimeError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"A crawl run is already running: {run_id}")


class CrawlRunStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._database = LocalDatabase(database_path)

    def ensure_store_reference(
        self,
        *,
        store_id: int,
        store_name: str,
        platform_store_id: str,
        platform_code: str = "tmall",
        platform_name: str = "天猫",
    ) -> int:
        """Ensure the ledger's foreign keys exist before a run is created."""
        now = self._now()
        with self._connect(initialize=True) as conn:
            platform_row = conn.execute(
                f"select {q(PLATFORM_ID)} as platform_id from platforms "
                f"where {q(PLATFORM_CODE)} = ?",
                (platform_code,),
            ).fetchone()
            if platform_row is None:
                platform_row = conn.execute(
                    f"select coalesce(max({q(PLATFORM_ID)}), 0) + 1 as platform_id "
                    "from platforms"
                ).fetchone()
                platform_id = int(platform_row["platform_id"])
                conn.execute(
                    f"""
                    insert into platforms (
                        {q(PLATFORM_ID)}, {q(PLATFORM_CODE)}, {q(PLATFORM_NAME)},
                        {q(STATUS)}, {q(CREATED_AT)}, {q(UPDATED_AT)}
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (platform_id, platform_code, platform_name, "active", now, now),
                )
            else:
                platform_id = int(platform_row["platform_id"])
                conn.execute(
                    f"update platforms set {q(PLATFORM_NAME)} = ?, {q(STATUS)} = ?, "
                    f"{q(UPDATED_AT)} = ? where {q(PLATFORM_ID)} = ?",
                    (platform_name, "active", now, platform_id),
                )

            store_row = conn.execute(
                f"select {q(STORE_ID)} as store_id, {q(FIRST_SEEN_AT)} as first_seen_at "
                f"from stores where {q(STORE_ID)} = ?",
                (store_id,),
            ).fetchone()
            if store_row is None:
                conn.execute(
                    f"""
                    insert into stores (
                        {q(STORE_ID)}, {q(PLATFORM_ID)}, {q(STORE_SUBJECT_ID)},
                        {q(STORE_NAME)}, {q(STATUS)}, {q(FIRST_SEEN_AT)}, {q(UPDATED_AT)}
                    ) values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        store_id,
                        platform_id,
                        platform_store_id,
                        store_name,
                        "active",
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    f"""
                    update stores
                    set {q(PLATFORM_ID)} = ?, {q(STORE_SUBJECT_ID)} = ?,
                        {q(STORE_NAME)} = ?, {q(STATUS)} = ?, {q(UPDATED_AT)} = ?
                    where {q(STORE_ID)} = ?
                    """,
                    (
                        platform_id,
                        platform_store_id,
                        store_name,
                        "active",
                        now,
                        store_id,
                    ),
                )
            conn.commit()
        return store_id

    def create_run(
        self,
        *,
        store_id: int,
        task_type: str,
        start_day: date,
        end_day: date,
        mode: str,
        planned_days: int,
        log_file: Path,
    ) -> str:
        now = self._now()
        run_id = (
            f"crawl_{task_type}_{start_day:%Y%m%d}_{end_day:%Y%m%d}_"
            f"{datetime.now():%H%M%S%f}"
        )
        with self._connect(initialize=True) as conn:
            conn.execute("begin immediate")
            active = conn.execute(
                f"""
                select {q(CRAWL_RUN_ID)} as run_id
                from crawl_runs
                where {q(STORE_ID)} = ?
                  and {q(CRAWL_TASK_TYPE)} = ?
                  and {q(RUN_STATUS)} = 'running'
                order by {q(STARTED_AT)} desc
                limit 1
                """,
                (store_id, task_type),
            ).fetchone()
            if active is not None:
                raise CrawlRunAlreadyRunning(str(active["run_id"]))
            conn.execute(
                f"""
                insert into crawl_runs (
                    {q(CRAWL_RUN_ID)}, {q(STORE_ID)}, {q(CRAWL_TASK_TYPE)},
                    {q(START_DAY)}, {q(END_DAY)}, {q(RUN_MODE)}, {q(RUN_STATUS)},
                    {q(PLANNED_DAYS)}, {q(SUCCESS_DAYS)}, {q(SKIPPED_DAYS)},
                    {q(FAILED_DAYS)}, {q(STARTED_AT)}, {q(FINISHED_AT)}, {q(LOG_FILE)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    store_id,
                    task_type,
                    start_day.isoformat(),
                    end_day.isoformat(),
                    mode,
                    "running",
                    planned_days,
                    0,
                    0,
                    0,
                    now,
                    None,
                    str(log_file),
                ),
            )
            self._refresh_run_counts(conn, run_id)
            conn.commit()
        return run_id

    def record_day(
        self,
        *,
        run_id: str,
        store_id: int,
        business_day: date,
        status: str,
        metric_count: int | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._connect(initialize=True) as conn:
            conn.execute(
                f"""
                insert into crawl_run_days (
                    {q(CRAWL_RUN_ID)}, {q(STORE_ID)}, {q(BUSINESS_DAY)},
                    {q(DAY_STATUS)}, {q(METRIC_COUNT)}, {q(ERROR_MESSAGE)}
                ) values (?, ?, ?, ?, ?, ?)
                on conflict({q(CRAWL_RUN_ID)}, {q(BUSINESS_DAY)}) do update set
                    {q(DAY_STATUS)} = excluded.{q(DAY_STATUS)},
                    {q(METRIC_COUNT)} = excluded.{q(METRIC_COUNT)},
                    {q(ERROR_MESSAGE)} = excluded.{q(ERROR_MESSAGE)}
                """,
                (
                    run_id,
                    store_id,
                    business_day.isoformat(),
                    status,
                    metric_count,
                    error_message,
                ),
            )
            self._refresh_run_counts(conn, run_id)
            conn.commit()

    def finish_run(
        self,
        *,
        run_id: str,
        status: str,
        success_days: int,
        skipped_days: int,
        failed_days: int,
    ) -> None:
        with self._connect(initialize=True) as conn:
            conn.execute(
                f"""
                update crawl_runs
                set {q(RUN_STATUS)} = ?,
                    {q(SUCCESS_DAYS)} = ?,
                    {q(SKIPPED_DAYS)} = ?,
                    {q(FAILED_DAYS)} = ?,
                    {q(FINISHED_AT)} = ?
                where {q(CRAWL_RUN_ID)} = ?
                """,
                (
                    status,
                    success_days,
                    skipped_days,
                    failed_days,
                    self._now(),
                    run_id,
                ),
            )
            self._refresh_run_counts(conn, run_id)
            conn.commit()

    def fail_running_run_for_timeout(
        self,
        *,
        store_id: int,
        task_type: str,
        business_day: date,
        error_message: str,
    ) -> str | None:
        """Close a worker ledger that was terminated by its parent process.

        A daily orchestrator can terminate a child after its wall-clock
        timeout.  The child may already have created a ``crawl_runs`` row but
        never get a chance to execute its normal ``finally`` block.  Locate
        only the matching active run and persist the failed day before closing
        it, so the coverage API never leaves a permanent ``running`` state.
        """
        with self._connect(initialize=True) as conn:
            row = conn.execute(
                f"""
                select {q(CRAWL_RUN_ID)} as run_id,
                       {q(START_DAY)} as start_day,
                       {q(END_DAY)} as end_day
                from crawl_runs
                where {q(STORE_ID)} = ?
                  and {q(CRAWL_TASK_TYPE)} = ?
                  and {q(START_DAY)} <= ?
                  and {q(END_DAY)} >= ?
                  and {q(RUN_STATUS)} = 'running'
                order by datetime({q(STARTED_AT)}) desc
                limit 1
                """,
                (
                    store_id,
                    task_type,
                    business_day.isoformat(),
                    business_day.isoformat(),
                ),
            ).fetchone()
            if row is None:
                return None
            run_id = str(row["run_id"])
            recorded_days = {
                str(day_row["business_day"])
                for day_row in conn.execute(
                    f"""
                    select {q(BUSINESS_DAY)} as business_day
                    from crawl_run_days
                    where {q(CRAWL_RUN_ID)} = ?
                    """,
                    (run_id,),
                ).fetchall()
            }
            start_day = date.fromisoformat(str(row["start_day"]))
            end_day = date.fromisoformat(str(row["end_day"]))
            day_cursor = start_day
            while day_cursor <= end_day:
                day_value = day_cursor.isoformat()
                if day_value not in recorded_days:
                    conn.execute(
                        f"""
                        insert into crawl_run_days (
                            {q(CRAWL_RUN_ID)}, {q(STORE_ID)}, {q(BUSINESS_DAY)},
                            {q(DAY_STATUS)}, {q(METRIC_COUNT)}, {q(ERROR_MESSAGE)}
                        ) values (?, ?, ?, 'fetch_failed', null, ?)
                        """,
                        (run_id, store_id, day_value, error_message),
                    )
                day_cursor = date.fromordinal(day_cursor.toordinal() + 1)
            conn.execute(
                f"""
                update crawl_runs
                set {q(RUN_STATUS)} = 'completed_with_errors',
                    {q(FINISHED_AT)} = ?
                where {q(CRAWL_RUN_ID)} = ?
                """,
                (self._now(), run_id),
            )
            self._refresh_run_counts(conn, run_id)
            return run_id

    def list_runs(self, limit: int = 20) -> CrawlRunList:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select *
                from crawl_runs
                order by datetime({q(STARTED_AT)}) desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return CrawlRunList(runs=[self._run_from_row(row) for row in rows])

    def get_detail(self, run_id: str) -> CrawlRunDetail:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                select *
                from crawl_runs
                where {q(CRAWL_RUN_ID)} = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise CrawlRunMissing(f"Crawl run not found: {run_id}")
            day_rows = conn.execute(
                f"""
                select *
                from crawl_run_days
                where {q(CRAWL_RUN_ID)} = ?
                order by {q(BUSINESS_DAY)}
                """,
                (run_id,),
            ).fetchall()
        return CrawlRunDetail(
            **self._run_from_row(row).model_dump(),
            days=[self._day_from_row(day_row) for day_row in day_rows],
        )

    @contextmanager
    def _connect(self, *, initialize: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self._database.connect(initialize=initialize)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _refresh_run_counts(conn: sqlite3.Connection, run_id: str) -> None:
        conn.execute(
            f"""
            update crawl_runs
                set {q(SUCCESS_DAYS)} = (
                    select count(*) from crawl_run_days
                    where {q(CRAWL_RUN_ID)} = ? and {q(DAY_STATUS)} in ('ingested', 'no_data')
                ),
                {q(SKIPPED_DAYS)} = (
                    select count(*) from crawl_run_days
                    where {q(CRAWL_RUN_ID)} = ? and {q(DAY_STATUS)} = 'skipped_existing'
                ),
                {q(FAILED_DAYS)} = (
                    select count(*) from crawl_run_days
                    where {q(CRAWL_RUN_ID)} = ? and {q(DAY_STATUS)} like '%failed'
                )
            where {q(CRAWL_RUN_ID)} = ?
            """,
            (run_id, run_id, run_id, run_id),
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> CrawlRun:
        return CrawlRun(
            run_id=row[CRAWL_RUN_ID],
            store_id=row[STORE_ID],
            task_type=row[CRAWL_TASK_TYPE],
            start_day=row[START_DAY],
            end_day=row[END_DAY],
            mode=row[RUN_MODE],
            status=row[RUN_STATUS],
            planned_days=row[PLANNED_DAYS],
            success_days=row[SUCCESS_DAYS],
            skipped_days=row[SKIPPED_DAYS],
            failed_days=row[FAILED_DAYS],
            started_at=row[STARTED_AT],
            finished_at=row[FINISHED_AT],
            log_file=row[LOG_FILE],
        )

    @staticmethod
    def _day_from_row(row: sqlite3.Row) -> CrawlRunDay:
        return CrawlRunDay(
            item_id=row[ITEM_DAY_ID],
            run_id=row[CRAWL_RUN_ID],
            store_id=row[STORE_ID],
            business_day=row[BUSINESS_DAY],
            status=row[DAY_STATUS],
            metric_count=row[METRIC_COUNT],
            error_message=row[ERROR_MESSAGE],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
