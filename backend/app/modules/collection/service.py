from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from app.core.business_days import SHANGHAI_TZ, yesterday_in_shanghai
from app.core.config import PROJECT_ROOT, settings
from app.core.local_database import (
    BUSINESS_DAY,
    CRAWL_RUN_ID,
    CRAWL_TASK_TYPE,
    DAY_STATUS,
    ERROR_MESSAGE,
    RUN_STATUS,
    STARTED_AT,
    START_DAY,
    END_DAY,
    STORE_ID,
    LocalDatabase,
    q,
)
from app.modules.collection.registry import (
    COLLECTION_DATASET_BY_KEY,
    COLLECTION_DATASET_KEYS,
    COLLECTION_DATASETS,
    COVERAGE_SNAPSHOT_DATASET_NAMES,
    CollectionDataset,
)
from app.modules.collection.locks import active_feedback_run
from app.modules.collection.schemas import (
    CollectionBatch,
    CollectionBatchFailure,
    CollectionOverview,
    CollectionSchedule,
    DatasetCoverage,
    DatasetTableCoverage,
    DayCoverage,
)


logger = logging.getLogger(__name__)


class CollectionBatchConflict(RuntimeError):
    pass


class CollectionConfigurationError(ValueError):
    pass


class CollectionService:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = Path(database_path or settings.local_database_path).resolve()
        self.database = LocalDatabase(self.database_path)
        self.database.initialize_schema()

    def overview(self, *, target_day: date | None = None, recent_day_count: int = 7) -> CollectionOverview:
        day = target_day or yesterday_in_shanghai()
        self._reconcile_stale_batches()
        with self.database.connect() as conn:
            datasets = [self._dataset_coverage(conn, dataset, day) for dataset in COLLECTION_DATASETS]
            recent_days = [
                self._day_coverage(conn, day - timedelta(days=offset))
                for offset in reversed(range(max(1, recent_day_count)))
            ]
            latest_batch = self._latest_batch(conn)
            schedule = self._get_schedule(conn)

        counts = {status: sum(item.status == status for item in datasets) for status in (
            "complete", "partial", "missing", "failed", "no_data", "collecting"
        )}
        accepted = counts["complete"] + counts["no_data"]
        total = len(datasets)
        return CollectionOverview(
            target_day=day.isoformat(),
            generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            total_datasets=total,
            complete_count=counts["complete"],
            partial_count=counts["partial"],
            missing_count=counts["missing"],
            failed_count=counts["failed"],
            no_data_count=counts["no_data"],
            collecting_count=counts["collecting"],
            coverage_percent=round(accepted / total * 100) if total else 100,
            datasets=datasets,
            recent_days=recent_days,
            latest_batch=latest_batch,
            schedule=schedule,
        )

    def start_batch(
        self,
        *,
        business_day: date,
        dataset_names: Iterable[str] | None,
        session_source: str,
        refresh_existing: bool,
        trigger: str,
        resume_from_latest: bool = False,
    ) -> CollectionBatch:
        names = self._validate_dataset_names(dataset_names)
        feedback_run = active_feedback_run(self.database_path)
        if feedback_run is not None:
            feedback_label, run_id = feedback_run
            raise CollectionBatchConflict(
                f"{feedback_label}采集任务正在运行（{run_id}），请等待完成后再启动日常经营采集。"
            )
        if session_source not in {"env", "drissionpage"}:
            raise CollectionConfigurationError("session_source must be env or drissionpage")
        now = datetime.now().astimezone()
        batch_id = f"batch_{business_day:%Y%m%d}_{now:%H%M%S}_{uuid.uuid4().hex[:6]}"
        log_dir = self.database_path.parent / "daily_collection" / "batches"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{batch_id}.log"
        with self.database.connect(read_only=False) as conn:
            conn.execute("begin immediate")
            self._reconcile_running_batches(conn, commit=False)
            active = conn.execute(
                "select batch_id from collection_batches where status = 'running' limit 1"
            ).fetchone()
            if active is not None:
                conn.rollback()
                raise CollectionBatchConflict(f"采集批次正在运行：{active['batch_id']}")
            cursor = conn.execute(
                """
                insert into collection_batches (
                    batch_id, business_day, dataset_names_json, trigger_type,
                    session_source, refresh_existing, status, started_at, log_file
                )
                select ?, ?, ?, ?, ?, ?, 'running', ?, ?
                where not exists (
                    select 1 from collection_batches where status = 'running'
                )
                """,
                (
                    batch_id, business_day.isoformat(), json.dumps(names, ensure_ascii=False),
                    trigger, session_source, int(refresh_existing), now.isoformat(timespec="seconds"),
                    str(log_path),
                ),
            )
            if cursor.rowcount != 1:
                active = conn.execute(
                    "select batch_id from collection_batches where status = 'running' limit 1"
                ).fetchone()
                conn.rollback()
                raise CollectionBatchConflict(
                    f"采集批次正在运行：{active['batch_id'] if active else 'unknown'}"
                )
            conn.commit()

        # Respect the caller's dataset scope.  Historically every manual
        # single-dataset retry also appended the comparatively heavy market
        # collector, which made a focused retry wait on unrelated requests and
        # hid the real completion time from the operator.
        command_names = list(names)
        command = [
            sys.executable,
            str(PROJECT_ROOT / "backend" / "scripts" / "collect_daily.py"),
            "--day", business_day.isoformat(),
            "--datasets", ",".join(command_names),
            "--session-source", session_source,
            "--database-path", str(self.database_path),
        ]
        if any(name in {
            "cps_overviews",
            "brandsearch_reports",
            "alimama_campaigns",
            "alimama_crowds",
            "alimama_promotion_details",
            "alimama_adgroup_bidwords",
        } for name in names):
            command.extend(["--promotion-refresh-days", "15"])
        if refresh_existing:
            command.append("--refresh-existing")
        if resume_from_latest:
            command.append("--resume-from-latest")
        log_handle = log_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
        except Exception as exc:
            log_handle.close()
            self._finish_batch(batch_id, status="failed", error_message=str(exc))
            raise
        with self.database.connect(read_only=False) as conn:
            conn.execute(
                "update collection_batches set process_id = ? where batch_id = ?",
                (process.pid, batch_id),
            )
            conn.commit()
        threading.Thread(
            target=self._monitor_process,
            args=(batch_id, business_day, names, process, log_handle),
            daemon=True,
            name=f"collection-{batch_id}",
        ).start()
        return self.get_batch(batch_id)

    def get_batch(self, batch_id: str) -> CollectionBatch:
        self._reconcile_stale_batches()
        with self.database.connect() as conn:
            row = conn.execute(
                "select * from collection_batches where batch_id = ?", (batch_id,)
            ).fetchone()
        if row is None:
            raise KeyError(batch_id)
        return self._batch_from_row(row)

    def list_batches(self, limit: int = 20) -> list[CollectionBatch]:
        self._reconcile_stale_batches()
        with self.database.connect() as conn:
            rows = conn.execute(
                "select * from collection_batches order by datetime(started_at) desc limit ?",
                (limit,),
            ).fetchall()
        return [self._batch_from_row(row) for row in rows]

    def get_schedule(self) -> CollectionSchedule:
        with self.database.connect() as conn:
            return self._get_schedule(conn)

    def update_schedule(
        self,
        *,
        enabled: bool,
        run_time: str,
        dataset_names: Iterable[str] | None,
        session_source: str,
    ) -> CollectionSchedule:
        self._parse_run_time(run_time)
        names = self._validate_dataset_names(dataset_names)
        if session_source not in {"env", "drissionpage"}:
            raise CollectionConfigurationError("session_source must be env or drissionpage")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.database.connect(read_only=False) as conn:
            conn.execute(
                """
                insert into collection_schedule (
                    schedule_id, enabled, run_time, timezone, dataset_names_json,
                    session_source, updated_at
                ) values (1, ?, ?, 'Asia/Shanghai', ?, ?, ?)
                on conflict(schedule_id) do update set
                    enabled = excluded.enabled,
                    run_time = excluded.run_time,
                    dataset_names_json = excluded.dataset_names_json,
                    session_source = excluded.session_source,
                    updated_at = excluded.updated_at
                """,
                (int(enabled), run_time, json.dumps(names, ensure_ascii=False), session_source, now),
            )
            conn.commit()
            return self._get_schedule(conn)

    def trigger_schedule_if_due(self, *, now: datetime | None = None) -> CollectionBatch | None:
        current = (now or datetime.now(SHANGHAI_TZ)).astimezone(SHANGHAI_TZ)
        schedule = self.get_schedule()
        if not schedule.enabled:
            return None
        scheduled_time = self._parse_run_time(schedule.run_time)
        if current.time().replace(second=0, microsecond=0) < scheduled_time:
            return None
        target_day = current.date() - timedelta(days=1)
        if schedule.last_triggered_day == target_day.isoformat():
            return None
        # Daily collection resumes from each dataset's own completed coverage,
        # rather than assuming that a dataset complete on ``target_day`` has
        # no historical gap.  The child planner keeps this bounded and also
        # refreshes the short report-latency window for delayed platforms.
        coverage = self.overview(target_day=target_day, recent_day_count=1)
        attention_items = [
            item for item in coverage.datasets
            if item.status not in {"complete", "no_data"}
        ]
        selected_names = list(schedule.dataset_names)
        refresh_existing = any(
            item.key in selected_names and item.status == "partial"
            for item in attention_items
        )
        try:
            batch = self.start_batch(
                business_day=target_day,
                dataset_names=selected_names,
                session_source=schedule.session_source,
                refresh_existing=refresh_existing,
                trigger="schedule",
                resume_from_latest=True,
            )
        except CollectionBatchConflict:
            return None
        with self.database.connect(read_only=False) as conn:
            conn.execute(
                """
                update collection_schedule
                set last_triggered_day = ?, last_triggered_at = ?, updated_at = ?
                where schedule_id = 1
                """,
                (
                    target_day.isoformat(), current.isoformat(timespec="seconds"),
                    current.isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
        return batch

    def _dataset_coverage(self, conn, dataset: CollectionDataset, day: date) -> DatasetCoverage:
        table_states = [
            self._table_coverage_for_dataset(conn, dataset, table, day)
            for table in dataset.tables
        ]
        present_count = sum(table.present for table in table_states)
        run_rows = self._latest_task_attempts(conn, dataset, day)
        last_attempt = str(run_rows[0]["started_at"]) if run_rows else None
        # Keep the newest attempt for each worker type. Historical failures
        # stay in the task history, but a successful retry of the same worker
        # must clear its old error from the current coverage view.
        latest_attempts = []
        seen_task_types: set[str] = set()
        for row in run_rows:
            row_keys = row.keys() if hasattr(row, "keys") else row
            task_type = str(row["task_type"] or "") if "task_type" in row_keys else dataset.task_types[0]
            if task_type in seen_task_types:
                continue
            seen_task_types.add(task_type)
            latest_attempts.append(row)
        statuses = {str(row["day_status"]) for row in latest_attempts if row["day_status"]}
        last_run_status = str(latest_attempts[0]["run_status"]) if latest_attempts and latest_attempts[0]["run_status"] else None
        error = next((str(row["error_message"]) for row in latest_attempts if row["error_message"]), None)
        # A worker can fail during browser/session preflight, before it has a
        # chance to create a crawl_runs row.  Collection batches still retain
        # the failed child and its concise error, so surface that failure in
        # the dataset coverage instead of mislabelling it as "未到达".
        batch_failure = (
            self._latest_batch_failure(conn, dataset, day)
            if not latest_attempts and hasattr(conn, "execute")
            else None
        )
        if not latest_attempts and batch_failure is not None:
            batch_started_at, batch_error = batch_failure
            last_attempt = batch_started_at
            last_run_status = "failed"
            error = batch_error

        # These tables intentionally use a filtered notion of coverage (for
        # example, a new-customer response may contain only shop-level fields).
        # Keep the raw row count in the API and explain the placeholder rather
        # than presenting it as an unexplained empty day.
        if (
            dataset.key == "sycm_new_customer_discount"
            and any(table.raw_row_count > 0 and not table.present for table in table_states)
        ):
            error = error or "接口已返回店铺级数据，但活动级新客指标为空，尚未形成完整日报。"

        # U先 returns the two reports independently.  A successful report with
        # zero rows is an explicit platform no-data result for that sub-table;
        # it is covered and should not make the two-table dataset look missing.
        utry_no_data_tables = 0
        if dataset.key == "utry_overviews" and "ingested" in statuses:
            for table in table_states:
                if not table.present and table.raw_row_count == 0:
                    table.present = True
                    table.status = "no_data"
                    utry_no_data_tables += 1
            present_count = sum(table.present for table in table_states)
        # Coverage snapshots replace their owned current-state tables after a
        # successful response.  The crawl run is therefore the authoritative
        # coverage marker even when the valid replacement contains zero rows.
        # Row presence alone must not turn a completed refresh into "部分缺失".
        successful_empty_capable_snapshot = (
            dataset.collection_mode == "coverage_snapshot"
            and "ingested" in statuses
        )
        if successful_empty_capable_snapshot:
            for table in table_states:
                if not table.present and table.raw_row_count == 0:
                    table.present = True
                    table.status = "no_data"
            present_count = sum(table.present for table in table_states)
        if dataset.key == "utry_overviews" and table_states and all(
            table.status == "no_data" for table in table_states
        ):
            status = "no_data"
        elif present_count == len(table_states) or successful_empty_capable_snapshot:
            status = "complete"
        elif present_count:
            status = "partial"
        elif (
            dataset.key == "sycm_new_customer_discount"
            and any(table.status == "partial" for table in table_states)
        ):
            status = "partial"
        elif "running" in {str(row["run_status"]) for row in latest_attempts}:
            status = "collecting"
        elif batch_failure is not None:
            status = "failed"
        elif any(value.endswith("failed") for value in statuses):
            status = "failed"
        elif dataset.allow_no_data and "no_data" in statuses:
            status = "no_data"
        else:
            status = "missing"

        # A later successful ingestion is authoritative for the coverage
        # view. Keep prior task failures in the run history, but do not attach
        # them to a dataset that is now complete or explicitly has no data.
        if status in {"complete", "no_data"}:
            error = None
        else:
            error = self._coverage_error_message(error)
        return DatasetCoverage(
            key=dataset.key,
            label=dataset.label,
            group=dataset.group,
            description=dataset.description,
            collection_mode=dataset.collection_mode,
            status=status,
            target_day=day.isoformat(),
            present_tables=present_count,
            expected_tables=len(table_states),
            row_count=sum(item.row_count for item in table_states),
            latest_date=max((item.latest_date for item in table_states if item.latest_date), default=None),
            last_attempt_at=last_attempt,
            last_run_status=last_run_status,
            error_message=error,
            tables=table_states,
        )

    @staticmethod
    def _coverage_error_message(error: str | None) -> str | None:
        """Normalize known worker errors into concise operator guidance."""
        if error == (
            "The SYCM BYBT overview response is incomplete; required traffic "
            "and transaction metrics are missing."
        ):
            return (
                "百亿补贴接口未返回流量和成交指标（访客、支付买家、支付金额、"
                "支付订单、支付件数）；请确认百亿补贴页面权限后重试。"
            )
        return error

    def _latest_batch_failure(
        self,
        conn,
        dataset: CollectionDataset,
        day: date,
    ) -> tuple[str, str] | None:
        """Return a failed collection-batch attempt when no crawl run exists."""
        rows = conn.execute(
            "select started_at, status, log_file, dataset_names_json "
            "from collection_batches where business_day = ? "
            "order by datetime(started_at) desc",
            (day.isoformat(),),
        ).fetchall()
        for row in rows:
            try:
                names = json.loads(row["dataset_names_json"] or "[]")
            except (TypeError, json.JSONDecodeError):
                names = []
            if dataset.key not in names:
                continue
            failures = self._batch_log_failures(str(row["log_file"] or ""))
            if dataset.key in failures:
                return str(row["started_at"]), failures[dataset.key]
            # A collection batch can be marked completed_with_errors because a
            # different dataset failed (or because the outer summary exited
            # non-zero).  Only a dataset-specific failed event is evidence for
            # this dataset, so keep looking rather than mislabelling a valid
            # partial response as failed.
        return None

    def _table_coverage_for_dataset(
        self,
        conn,
        dataset: CollectionDataset,
        table: str,
        day: date,
    ) -> DatasetTableCoverage:
        if dataset.scope == "store":
            return self._table_coverage(conn, table, day)
        exists = conn.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?", (table,)
        ).fetchone()
        if exists is None:
            return DatasetTableCoverage(table=table, present=False, status="missing")
        date_column = "stat_end" if dataset.scope == "market" else BUSINESS_DAY
        row = conn.execute(
            f"select count(*) as row_count from {q(table)} where {q(date_column)} = ?",
            (day.isoformat(),),
        ).fetchone()
        latest = conn.execute(
            f"select max({q(date_column)}) as latest_date from {q(table)}"
        ).fetchone()
        return DatasetTableCoverage(
            table=table,
            present=int(row["row_count"] or 0) > 0,
            row_count=int(row["row_count"] or 0),
            raw_row_count=int(row["row_count"] or 0),
            latest_date=str(latest["latest_date"])
            if latest and latest["latest_date"] else None,
            status="complete" if int(row["row_count"] or 0) > 0 else "missing",
        )

    def _table_coverage(self, conn, table: str, day: date) -> DatasetTableCoverage:
        exists = conn.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?", (table,)
        ).fetchone()
        if exists is None:
            return DatasetTableCoverage(table=table, present=False, status="missing")
        where = f"where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?"
        parameters: tuple[object, ...] = (settings.default_store_id or 1, day.isoformat())
        required_filter = ""
        if table == "store_daily_bybt_overviews":
            # A successful HTTP response can contain only the online-item
            # placeholder while traffic and transaction metrics are absent.
            # Such a row is not daily coverage and must remain retryable.
            required_filter = (
                ' and "百补访客数" is not null'
                ' and "百补支付买家数" is not null'
                ' and "百补支付金额" is not null'
                ' and "百补子订单数" is not null'
                ' and "百补支付成交件数" is not null'
            )
        elif table == "store_daily_new_customer_discount_overviews":
            # The endpoint may return only the shop-level new-customer
            # comparison. That row is partial and must remain retryable until
            # the four activity-level fields arrive.
            required_filter = (
                ' and "商品新访客数" is not null'
                ' and "新客支付人数" is not null'
                ' and "新客支付金额" is not null'
                ' and "新客支付转化率" is not null'
            )
        elif table == "store_daily_taobao_flash_sale_overviews":
            # An HTTP 200 empty response is a valid platform no-data result,
            # but a row containing only NULL metrics is not daily coverage.
            # Keep it retryable unless the crawl run explicitly records
            # ``no_data``.
            required_filter = (
                ' and "活动中商品量级" is not null'
                ' and "活动商品IPV" is not null'
                ' and "活动商品IPVUV" is not null'
                ' and "活动商品成交笔数" is not null'
                ' and "活动商品成交金额" is not null'
                ' and "活动商品引导店铺新客" is not null'
                ' and "活动商品最高爆发系数" is not null'
            )
        where += required_filter
        raw_row = conn.execute(
            f"select count(*) as row_count from {q(table)} "
            f"where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?",
            parameters[:2],
        ).fetchone()
        row = conn.execute(
            f"select count(*) as row_count from {q(table)} {where}",
            parameters,
        ).fetchone()
        latest = conn.execute(
            f"select max({q(BUSINESS_DAY)}) as latest_date from {q(table)} "
            f"where {q(STORE_ID)} = ?"
            + required_filter,
            (settings.default_store_id or 1,),
        ).fetchone()
        count = int(row["row_count"] or 0)
        raw_count = int(raw_row["row_count"] or 0)
        return DatasetTableCoverage(
            table=table,
            present=count > 0,
            row_count=count,
            raw_row_count=raw_count,
            latest_date=str(latest["latest_date"]) if latest and latest["latest_date"] else None,
            status="complete" if count > 0 else "partial" if raw_count > 0 else "missing",
        )

    @staticmethod
    def _latest_task_attempts(
        conn,
        dataset: CollectionDataset,
        day: date,
        started_after: str | None = None,
        started_before: str | None = None,
    ):
        placeholders = ",".join("?" for _ in dataset.task_types)
        started_filter = (
            f" and datetime(r.{q(STARTED_AT)}) >= datetime(?)" if started_after else ""
        ) + (
            f" and datetime(r.{q(STARTED_AT)}) <= datetime(?)" if started_before else ""
        )
        parameters: tuple[object, ...] = (
            day.isoformat(), *dataset.task_types, day.isoformat(), day.isoformat(),
            *((started_after,) if started_after else ()),
            *((started_before,) if started_before else ()),
        )
        return conn.execute(
            f"""
            select r.{q(CRAWL_TASK_TYPE)} as task_type,
                   r.{q(CRAWL_RUN_ID)} as crawl_run_id,
                   r.{q(RUN_STATUS)} as run_status,
                   r.{q(STARTED_AT)} as started_at,
                   d.{q(DAY_STATUS)} as day_status,
                   d.{q(ERROR_MESSAGE)} as error_message
            from crawl_runs r
            left join crawl_run_days d
              on d.{q(CRAWL_RUN_ID)} = r.{q(CRAWL_RUN_ID)}
             and d.{q(BUSINESS_DAY)} = ?
            where r.{q(CRAWL_TASK_TYPE)} in ({placeholders})
              and r.{q(START_DAY)} <= ? and r.{q(END_DAY)} >= ?
              and coalesce(d.{q(DAY_STATUS)}, '') <> 'skipped_existing'
              {started_filter}
            order by datetime(r.{q(STARTED_AT)}) desc
            """,
            parameters,
        ).fetchall()

    def _day_coverage(self, conn, day: date) -> DayCoverage:
        items = [self._dataset_coverage(conn, dataset, day) for dataset in COLLECTION_DATASETS]
        complete = sum(item.status == "complete" for item in items)
        no_data = sum(item.status == "no_data" for item in items)
        total = len(items)
        return DayCoverage(
            day=day.isoformat(),
            complete=complete,
            no_data=no_data,
            attention=total - complete - no_data,
            total=total,
            coverage_percent=round((complete + no_data) / total * 100) if total else 100,
        )

    def _monitor_process(self, batch_id, day, names, process, log_handle) -> None:
        return_code = process.wait()
        log_handle.close()
        overview = self.overview(target_day=day, recent_day_count=1)
        selected = [item for item in overview.datasets if item.key in names]
        completed = sum(item.status in {"complete", "no_data"} for item in selected)
        failed = len(selected) - completed
        self._finish_batch(
            batch_id,
            status="completed" if return_code == 0 and failed == 0 else "completed_with_errors",
            completed_count=completed,
            failed_count=failed,
            error_message=None if return_code == 0 else f"worker exited with code {return_code}",
        )

    def _finish_batch(
        self, batch_id: str, *, status: str, completed_count: int = 0,
        failed_count: int = 0, error_message: str | None = None,
    ) -> None:
        with self.database.connect(read_only=False) as conn:
            conn.execute(
                """
                update collection_batches set status = ?, completed_count = ?,
                    failed_count = ?, finished_at = ?, error_message = ?
                where batch_id = ?
                """,
                (
                    status, completed_count, failed_count,
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                    error_message, batch_id,
                ),
            )
            conn.commit()

    def _reconcile_running_batches(self, conn, *, commit: bool = True) -> None:
        rows = conn.execute(
            "select * from collection_batches where status = 'running'"
        ).fetchall()
        changed = False
        for row in rows:
            process_id = row["process_id"]
            if process_id is None or self._process_exists(int(process_id)):
                continue
            day = date.fromisoformat(str(row["business_day"]))
            names = json.loads(row["dataset_names_json"])
            selected = [
                self._dataset_coverage(conn, COLLECTION_DATASET_BY_KEY[name], day)
                for name in names
                if name in COLLECTION_DATASET_BY_KEY
            ]
            completed = sum(item.status in {"complete", "no_data"} for item in selected)
            failed = len(selected) - completed
            conn.execute(
                """
                update collection_batches
                set status = ?, completed_count = ?, failed_count = ?, finished_at = ?
                where batch_id = ? and status = 'running'
                """,
                (
                    "completed" if failed == 0 else "completed_with_errors",
                    completed,
                    failed,
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                    row["batch_id"],
                ),
            )
            changed = True
        if changed and commit:
            conn.commit()

    def _reconcile_stale_batches(self) -> None:
        with self.database.connect(read_only=False) as conn:
            self._reconcile_running_batches(conn)

    @staticmethod
    def _process_exists(process_id: int) -> bool:
        if sys.platform == "win32":
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information, False, process_id
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        try:
            os.kill(process_id, 0)
        except OSError:
            return False
        return True

    def _get_schedule(self, conn) -> CollectionSchedule:
        row = conn.execute("select * from collection_schedule where schedule_id = 1").fetchone()
        if row is None:
            return CollectionSchedule(
                dataset_names=list(COLLECTION_DATASET_KEYS),
                # Scheduled collection is intended to use the already logged
                # in browser by default.  Environment cookies remain available
                # as an explicit per-schedule option.
                session_source="drissionpage",
                next_run_at=None,
            )
        configured_names = json.loads(row["dataset_names_json"])
        # Migrate schedules created before the activity-calendar dataset was
        # registered.  Keep intentionally narrowed schedules unchanged.
        legacy_default_names = set(COLLECTION_DATASET_KEYS) - {"sycm_activity_calendar"}
        if (
            "sycm_activity_calendar" not in configured_names
            and set(configured_names) == legacy_default_names
        ):
            configured_names.append("sycm_activity_calendar")
        active_names = [
            name for name in configured_names
            if name in COLLECTION_DATASET_BY_KEY
        ]
        schedule = CollectionSchedule(
            enabled=bool(row["enabled"]),
            run_time=row["run_time"],
            timezone=row["timezone"],
            dataset_names=active_names,
            session_source=row["session_source"],
            last_triggered_day=row["last_triggered_day"],
            last_triggered_at=row["last_triggered_at"],
        )
        schedule.next_run_at = self._next_run_at(schedule)
        return schedule

    @staticmethod
    def _next_run_at(schedule: CollectionSchedule) -> str | None:
        if not schedule.enabled:
            return None
        zone = ZoneInfo(schedule.timezone)
        current = datetime.now(zone)
        value = CollectionService._parse_run_time(schedule.run_time)
        candidate = datetime.combine(current.date(), value, tzinfo=zone)
        if candidate <= current:
            candidate += timedelta(days=1)
        return candidate.isoformat(timespec="minutes")

    @staticmethod
    def _parse_run_time(value: str) -> clock_time:
        try:
            parsed = clock_time.fromisoformat(value)
        except ValueError as exc:
            raise CollectionConfigurationError("run_time must use HH:MM") from exc
        if parsed.second or parsed.microsecond:
            raise CollectionConfigurationError("run_time must use HH:MM")
        return parsed

    @staticmethod
    def _validate_dataset_names(names: Iterable[str] | None) -> list[str]:
        values = list(dict.fromkeys(names or COLLECTION_DATASET_KEYS))
        unknown = [name for name in values if name not in COLLECTION_DATASET_BY_KEY]
        if unknown:
            raise CollectionConfigurationError("未知数据集：" + ", ".join(unknown))
        if not values:
            raise CollectionConfigurationError("至少选择一个数据集")
        return values

    @staticmethod
    def _safe_batch_error(value: object | None) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
        if not text:
            return None
        # Do not expose cookies, tokens, or a full response body in the UI.
        for marker in ("cookie", "token", "authorization", "request headers", "请求头"):
            if marker in text.lower():
                return "采集会话或页面参数未就绪，请在采集浏览器中完成登录后重试。"
        return text[:320]

    def _batch_log_failures(self, log_file: str) -> dict[str, str]:
        """Read only the child worker's concise failure text from its batch log."""
        path = Path(log_file)
        if not path.is_file():
            return {}
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {}
        failures: dict[str, str] = {}
        # The parent process writes a terminal event before it writes the JSON
        # summary.  Surface that event immediately so a running batch can show
        # the failed dataset without waiting for the worker to exit.
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("[") or "] failed" not in stripped:
                continue
            try:
                label, remainder = stripped[1:].split("]", 1)
            except ValueError:
                continue
            dataset_key = label.split(":", 1)[0].strip()
            message = remainder[len(" failed"):].strip(" :-")
            safe = self._safe_batch_error(message) or "子任务已报告失败，请重试该数据集。"
            if dataset_key:
                failures[dataset_key] = safe

        decoder = json.JSONDecoder()
        summary: dict[str, object] | None = None
        cursor = 0
        while True:
            start = content.find("{", cursor)
            if start < 0:
                break
            try:
                candidate, consumed = decoder.raw_decode(content[start:])
            except json.JSONDecodeError:
                cursor = start + 1
                continue
            cursor = start + max(1, consumed)
            if isinstance(candidate, dict) and isinstance(candidate.get("results"), list):
                summary = candidate
        if summary is None:
            return failures
        for result in summary["results"]:
            if not isinstance(result, dict) or result.get("status") == "completed":
                continue
            dataset_key = str(result.get("dataset") or "").split(":", 1)[0]
            message = (
                result.get("error")
                or result.get("stderr")
                or result.get("stdout")
            )
            if isinstance(message, str) and "\n" in message:
                lines = [line.strip() for line in message.splitlines() if line.strip()]
                failure_lines = [
                    line for line in lines
                    if "failed" in line.lower() or "error" in line.lower()
                ]
                message = " ".join(failure_lines[:3] or lines[:1])
            safe = self._safe_batch_error(message)
            if dataset_key and safe:
                failures[dataset_key] = safe
        return failures

    @staticmethod
    def _batch_log_events(log_file: str) -> list[tuple[str, str]]:
        path = Path(log_file)
        if not path.is_file():
            return []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        events: list[tuple[str, str]] = []
        for line in lines:
            if not line.startswith("[") or "] " not in line:
                continue
            label, remainder = line[1:].split("] ", 1)
            action = remainder.split(" ", 1)[0]
            if action in {"collecting", "completed", "failed"}:
                events.append((label, action))
        return events

    def _batch_progress(self, conn, row) -> dict[str, object]:
        names = json.loads(row["dataset_names_json"] or "[]")
        day = date.fromisoformat(str(row["business_day"]))
        total = len(names)
        batch_started_at = str(row["started_at"] or "")
        batch_finished_at = str(row["finished_at"] or "") or None
        events = self._batch_log_events(str(row["log_file"] or ""))
        event_states: dict[str, dict[str, str]] = {}
        active_labels: list[str] = []
        for label, action in events:
            dataset_key = label.split(":", 1)[0]
            event_states.setdefault(dataset_key, {})[label] = action
            if action == "collecting":
                if label in active_labels:
                    active_labels.remove(label)
                active_labels.append(label)
            elif label in active_labels:
                active_labels.remove(label)
        coverages = [
            self._dataset_coverage(conn, COLLECTION_DATASET_BY_KEY[name], day)
            for name in names
            if name in COLLECTION_DATASET_BY_KEY
        ]
        coverage_by_key = {item.key: item for item in coverages}
        log_failures = self._batch_log_failures(str(row["log_file"] or ""))
        failed_from_attempts: set[str] = set()
        batch_attempts: dict[str, list] = {}
        for name in names:
            dataset = COLLECTION_DATASET_BY_KEY.get(name)
            if dataset is None:
                continue
            attempts = self._latest_task_attempts(
                conn, dataset, day, batch_started_at, batch_finished_at,
            )
            batch_attempts[name] = attempts
            if any(
                str(attempt["run_status"] or "") == "failed"
                or str(attempt["day_status"] or "").endswith("failed")
                for attempt in attempts
            ):
                failed_from_attempts.add(name)
        failed_keys = set(log_failures) | failed_from_attempts
        successes = [
            item for item in coverages
            if item.status in {"complete", "no_data"} and item.key not in failed_keys
        ]
        failures: list[CollectionBatchFailure] = []
        current: tuple[str, str, str] | None = None
        for name in names:
            dataset = COLLECTION_DATASET_BY_KEY.get(name)
            item = coverage_by_key.get(name)
            if dataset is None or item is None:
                continue
            attempts = self._latest_task_attempts(
                conn, dataset, day, batch_started_at, batch_finished_at,
            )
            latest = attempts[0] if attempts else None
            running = next((attempt for attempt in attempts if str(attempt["run_status"] or "") in {"queued", "running"}), None)
            if current is None and running is not None:
                current = (name, dataset.label, str(running["task_type"] or dataset.task_types[0]))
            current_attempts = batch_attempts.get(name, [])
            current_failed = any(
                str(attempt["run_status"] or "") == "failed"
                or str(attempt["day_status"] or "").endswith("failed")
                for attempt in current_attempts
            )
            is_failed = name in log_failures or current_failed or (
                str(row["status"] or "") != "running" and item.status == "failed"
            )
            if is_failed:
                current_latest = current_attempts[0] if current_attempts else latest
                task_type = str(current_latest["task_type"] or dataset.task_types[0]) if current_latest else dataset.task_types[0]
                run_id = str(current_latest["crawl_run_id"]) if current_latest and current_latest["crawl_run_id"] else None
                error = self._safe_batch_error(item.error_message)
                if not error and current_latest is not None:
                    error = self._safe_batch_error(current_latest["error_message"])
                if not error:
                    error = log_failures.get(name)
                failures.append(CollectionBatchFailure(
                    dataset_key=name,
                    dataset_label=dataset.label,
                    task_type=task_type,
                    run_id=run_id,
                    status=item.status if item.status == "failed" else "failed",
                    error_message=error or "目标日期未完成入库，请查看采集浏览器页面后重试。",
                ))

        if str(row["status"] or "") != "running":
            recorded = {item.dataset_key for item in failures}
            for name in names:
                if name in recorded or name in {item.key for item in successes}:
                    continue
                dataset = COLLECTION_DATASET_BY_KEY.get(name)
                if dataset is None:
                    continue
                failures.append(CollectionBatchFailure(
                    dataset_key=name,
                    dataset_label=dataset.label,
                    status="incomplete",
                    error_message=(
                        log_failures.get(name)
                        or "子任务结束后未确认目标日期入库，请在采集浏览器中检查对应页面并重试。"
                    ),
                ))

        status = str(row["status"] or "")
        if status == "running":
            successful_keys: set[str] = set()
            failed_event_keys: set[str] = set()
            for name in names:
                dataset = COLLECTION_DATASET_BY_KEY.get(name)
                if dataset is None:
                    continue
                states = event_states.get(name, {})
                attempts = batch_attempts.get(name, [])
                terminal = [value for value in states.values() if value in {"completed", "failed"}]
                if "failed" in terminal:
                    failed_event_keys.add(name)
                elif attempts and all(
                    str(attempt["run_status"] or "") == "completed"
                    and not str(attempt["day_status"] or "").endswith("failed")
                    for attempt in attempts[:len(dataset.task_types)]
                ):
                    successful_keys.add(name)
                elif len(terminal) >= len(dataset.task_types):
                    successful_keys.add(name)
            failed_keys.update(failed_event_keys)
            completed_count = len(successful_keys)
            failed_count = len(failed_keys)
            settled = completed_count + failed_count
            current_label = active_labels[-1] if active_labels else None
            current_key = current_label.split(":", 1)[0] if current_label else None
            current_dataset = COLLECTION_DATASET_BY_KEY.get(current_key or "")
            current = (
                current_key,
                current_dataset.label,
                current_dataset.task_types[0],
            ) if current_key and current_dataset else None
            progress = round(settled / total * 100) if total else 100
            return {
                "total_count": total,
                "settled_count": min(total, settled),
                "progress_percent": min(100, progress),
                "success_rate": round(completed_count / total * 100, 1) if total else 100.0,
                "current_dataset_key": current[0] if current else None,
                "current_dataset_label": current[1] if current else None,
                "current_task_type": current[2] if current else None,
                "failure_details": failures,
                "completed_count": completed_count,
                "failed_count": failed_count,
            }
        settled = len(successes) + len(failures)
        if status != "running":
            # A finished worker has attempted every requested dataset, even if
            # a child did not produce a coverage row.
            settled = total
        completed_count = len(successes)
        failed_count = max(0, total - completed_count) if status != "running" else len(failures)
        progress = round(settled / total * 100) if total else 100
        success_rate = round(completed_count / total * 100, 1) if total else 100.0
        return {
            "total_count": total,
            "settled_count": min(total, settled),
            "progress_percent": min(100, progress),
            "success_rate": success_rate,
            "current_dataset_key": current[0] if current else None,
            "current_dataset_label": current[1] if current else None,
            "current_task_type": current[2] if current else None,
            "failure_details": failures,
            "completed_count": completed_count,
            "failed_count": failed_count,
        }

    def _batch_from_row(self, row, conn=None) -> CollectionBatch:
        owns_connection = conn is None
        connection = conn or self.database.connect()
        try:
            progress = self._batch_progress(connection, row)
            stored_status = str(row["status"] or "")
            display_status = stored_status
            if stored_status in {"completed", "completed_with_errors"}:
                display_status = (
                    "completed"
                    if int(progress["failed_count"]) == 0
                    else "completed_with_errors"
                )
            return CollectionBatch(
            batch_id=row["batch_id"],
            business_day=row["business_day"],
            dataset_names=json.loads(row["dataset_names_json"]),
            trigger=row["trigger_type"],
            session_source=row["session_source"],
            refresh_existing=bool(row["refresh_existing"]),
            status=display_status,
            process_id=row["process_id"],
            completed_count=int(progress["completed_count"]),
            failed_count=int(progress["failed_count"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            log_file=row["log_file"],
            error_message=row["error_message"],
            total_count=int(progress["total_count"]),
            settled_count=int(progress["settled_count"]),
            progress_percent=int(progress["progress_percent"]),
            success_rate=float(progress["success_rate"]),
            current_dataset_key=progress["current_dataset_key"],
            current_dataset_label=progress["current_dataset_label"],
            current_task_type=progress["current_task_type"],
            failure_details=progress["failure_details"],
            )
        finally:
            if owns_connection:
                connection.close()

    def _latest_batch(self, conn) -> CollectionBatch | None:
        row = conn.execute(
            "select * from collection_batches order by datetime(started_at) desc limit 1"
        ).fetchone()
        return self._batch_from_row(row, conn=conn) if row else None


class CollectionScheduler:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="collection-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        # Check immediately on API startup so a service restart does not add a
        # full polling interval to a due collection.  Keep the interval short
        # enough to react to a saved schedule within a few seconds while the
        # persisted target-day guard still prevents duplicate batches.
        poll_interval = 5.0
        backoff = poll_interval
        service: CollectionService | None = None
        while not self._stop_event.is_set():
            try:
                if service is None:
                    service = CollectionService()
                service.trigger_schedule_if_due()
                backoff = poll_interval
            except Exception:
                logger.exception("采集调度轮询失败")
                service = None
                backoff = min(backoff * 2, 60.0)
            self._stop_event.wait(backoff)


collection_scheduler = CollectionScheduler()
