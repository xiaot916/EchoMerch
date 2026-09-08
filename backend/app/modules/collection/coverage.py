from __future__ import annotations

"""Coverage rules shared by the status API and daily backfill planner."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.core.local_database import (
    BUSINESS_DAY,
    CRAWL_RUN_ID,
    CRAWL_TASK_TYPE,
    DAY_STATUS,
    END_DAY,
    ERROR_MESSAGE,
    RUN_STATUS,
    START_DAY,
    STARTED_AT,
    STORE_ID,
    q,
)
from app.modules.collection.registry import CollectionDataset


CoverageState = Literal[
    "complete",
    "no_data",
    "partial",
    "failed",
    "missing",
    "collecting",
]

DEFAULT_COVERAGE_WINDOW_DAYS = 30


# A row created from a sparse response must not close a business-day gap. These
# constraints mirror the API's table-level coverage checks and deliberately live
# here so the planner cannot disagree with the status page.
REQUIRED_TABLE_FILTERS: dict[str, str] = {
    "store_daily_customer_overviews": (
        ' and "店铺客户数" is not null'
        ' and "客户新访" is not null'
        ' and "新访成交" is not null'
        ' and "未购客户回访" is not null'
        ' and "回访成交" is not null'
        ' and "已购客户回访" is not null'
        ' and "老客复购" is not null'
        ' and "新访支付金额占比" is not null'
        ' and "未购回访支付金额占比" is not null'
        ' and "已购回访支付金额占比" is not null'
    ),
    "store_daily_bybt_overviews": (
        ' and "百补访客数" is not null'
        ' and "百补支付买家数" is not null'
        ' and "百补支付金额" is not null'
        ' and "百补子订单数" is not null'
        ' and "百补支付成交件数" is not null'
    ),
    "store_daily_new_customer_discount_overviews": (
        ' and "商品新访客数" is not null'
        ' and "新客支付人数" is not null'
        ' and "新客支付金额" is not null'
        ' and "新客支付转化率" is not null'
    ),
    "store_daily_taobao_flash_sale_overviews": (
        ' and "活动中商品量级" is not null'
        ' and "活动商品IPV" is not null'
        ' and "活动商品IPVUV" is not null'
        ' and "活动商品成交笔数" is not null'
        ' and "活动商品成交金额" is not null'
        ' and "活动商品引导店铺新客" is not null'
        ' and "活动商品最高爆发系数" is not null'
    ),
}


@dataclass(frozen=True)
class DatasetDayResolution:
    business_day: date
    status: CoverageState
    has_partial_rows: bool = False

    @property
    def resolved(self) -> bool:
        return self.status in {"complete", "no_data"}


@dataclass(frozen=True)
class DatasetGapAudit:
    target_day: date
    window_start: date
    anchor_day: date | None
    resolutions: tuple[DatasetDayResolution, ...]
    gap_dates: tuple[date, ...]
    contiguous_latest_day: date | None

    @property
    def backfill_start_day(self) -> date | None:
        return self.gap_dates[0] if self.gap_dates else None

    @property
    def requires_refresh(self) -> bool:
        return any(
            item.business_day in self.gap_dates and item.has_partial_rows
            for item in self.resolutions
        )

    @property
    def current(self) -> DatasetDayResolution:
        return self.resolutions[-1]


def audit_dataset_coverage(
    conn,
    dataset: CollectionDataset,
    *,
    target_day: date,
    window_days: int = DEFAULT_COVERAGE_WINDOW_DAYS,
    store_id: int = 1,
) -> DatasetGapAudit:
    """Audit the bounded, observed coverage history for one dataset.

    The first resolved day in the window is the local baseline. Days before it
    are intentionally not treated as gaps: a newly enabled dataset should not
    trigger an unbounded historical import. Once a baseline exists, every later
    unresolved day is a real discontinuity and is eligible for backfill.
    """

    if window_days < 1:
        raise ValueError("window_days must be at least one")
    window_start = target_day - timedelta(days=window_days - 1)
    resolutions = tuple(
        resolve_dataset_day(conn, dataset, business_day=window_start + timedelta(days=offset), store_id=store_id)
        for offset in range(window_days)
    )
    anchor_index = next((index for index, item in enumerate(resolutions) if item.resolved), None)
    if anchor_index is None:
        return DatasetGapAudit(
            target_day=target_day,
            window_start=window_start,
            anchor_day=None,
            resolutions=resolutions,
            gap_dates=(),
            contiguous_latest_day=None,
        )

    anchor_day = resolutions[anchor_index].business_day
    observed = resolutions[anchor_index:]
    gap_dates = tuple(item.business_day for item in observed if not item.resolved)
    contiguous_latest_day = anchor_day
    for item in observed[1:]:
        if not item.resolved:
            break
        contiguous_latest_day = item.business_day
    return DatasetGapAudit(
        target_day=target_day,
        window_start=window_start,
        anchor_day=anchor_day,
        resolutions=resolutions,
        gap_dates=gap_dates,
        contiguous_latest_day=contiguous_latest_day,
    )


def resolve_dataset_day(
    conn,
    dataset: CollectionDataset,
    *,
    business_day: date,
    store_id: int = 1,
) -> DatasetDayResolution:
    """Resolve one day using persisted facts and the crawl ledger.

    A generic ``ingested`` ledger entry is not enough to close a fact-table
    gap. It only means the HTTP request completed. Explicit ``no_data`` ledger
    rows and successfully refreshed coverage snapshots remain valid coverage.
    """

    attempts = _latest_day_attempts(conn, dataset, business_day=business_day, store_id=store_id)
    table_states = [
        _table_day_state(conn, dataset, table, business_day=business_day, store_id=store_id)
        for table in dataset.tables
    ]
    # A QPS response means the platform stopped a paginated read. A previous
    # snapshot can still be present for the date, but it is not proof that the
    # interrupted refresh reached every page.
    if _has_latest_qps_limit(
        conn,
        dataset,
        business_day=business_day,
        store_id=store_id,
    ):
        return DatasetDayResolution(
            business_day,
            "failed",
            has_partial_rows=any(state != "missing" for state in table_states),
        )
    if dataset.collection_mode == "coverage_snapshot" and _has_successful_snapshot_run(
        conn, dataset, business_day=business_day, store_id=store_id
    ):
        return DatasetDayResolution(business_day, "complete")
    if table_states and all(state == "complete" for state in table_states):
        return DatasetDayResolution(business_day, "complete")

    statuses = set(attempts.values())
    all_tasks_succeeded = (
        bool(dataset.task_types)
        and all(attempts.get(task_type) in {"ingested", "no_data"} for task_type in dataset.task_types)
    )
    if dataset.empty_report_tables and all_tasks_succeeded:
        # A report with no keyword-level rows is still a completed report when
        # its paired task completed successfully. Do not turn this explicit
        # platform result into an endlessly retried coverage gap.
        permitted_empty = {
            table
            for table, state in zip(dataset.tables, table_states, strict=True)
            if table in dataset.empty_report_tables and state == "missing"
        }
        if permitted_empty and all(
            state == "complete" or table in permitted_empty
            for table, state in zip(dataset.tables, table_states, strict=True)
        ):
            return DatasetDayResolution(
                business_day,
                "no_data" if len(permitted_empty) == len(table_states) else "complete",
            )
    if dataset.key == "utry_overviews" and all_tasks_succeeded:
        # U先 emits its two reports independently. An empty, successfully read
        # report is an explicit no-data component rather than a failed fetch.
        return DatasetDayResolution(
            business_day,
            "no_data" if statuses == {"no_data"} else "complete",
        )
    if dataset.allow_no_data and all_tasks_succeeded and statuses == {"no_data"}:
        return DatasetDayResolution(business_day, "no_data")
    if "running" in statuses:
        return DatasetDayResolution(business_day, "collecting")
    if any(status.endswith("failed") for status in statuses):
        return DatasetDayResolution(business_day, "failed")
    if any(state == "partial" for state in table_states):
        return DatasetDayResolution(business_day, "partial", has_partial_rows=True)
    return DatasetDayResolution(business_day, "missing")


def _has_latest_qps_limit(
    conn,
    dataset: CollectionDataset,
    *,
    business_day: date,
    store_id: int,
) -> bool:
    """Return whether a worker's newest attempt was stopped by platform QPS."""

    if not dataset.task_types:
        return False
    placeholders = ",".join("?" for _ in dataset.task_types)
    rows = conn.execute(
        f"""
        select r.{q(CRAWL_TASK_TYPE)} as task_type,
               d.{q(ERROR_MESSAGE)} as error_message
        from crawl_runs r
        inner join crawl_run_days d on d.{q(CRAWL_RUN_ID)} = r.{q(CRAWL_RUN_ID)}
        where d.{q(STORE_ID)} = ?
          and d.{q(BUSINESS_DAY)} = ?
          and r.{q(CRAWL_TASK_TYPE)} in ({placeholders})
        order by datetime(r.{q(STARTED_AT)}) desc
        """,
        (store_id, business_day.isoformat(), *dataset.task_types),
    ).fetchall()
    latest_errors: dict[str, str | None] = {}
    for row in rows:
        task_type = str(row["task_type"])
        if task_type not in latest_errors:
            latest_errors[task_type] = str(row["error_message"] or "")
    return any(_is_qps_limited_error(error) for error in latest_errors.values())


def _is_qps_limited_error(error_message: str | None) -> bool:
    normalized = (error_message or "").lower()
    return "qps" in normalized or "code 1800" in normalized or "code=1800" in normalized


def _table_day_state(conn, dataset: CollectionDataset, table: str, *, business_day: date, store_id: int) -> str:
    if not _table_exists(conn, table):
        return "missing"
    if dataset.scope == "store":
        where = f"where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?"
        parameters: tuple[object, ...] = (store_id, business_day.isoformat())
        required_filter = REQUIRED_TABLE_FILTERS.get(table, "")
        raw = conn.execute(
            f"select count(*) as row_count from {q(table)} {where}", parameters
        ).fetchone()
        valid = conn.execute(
            f"select count(*) as row_count from {q(table)} {where}{required_filter}", parameters
        ).fetchone()
    else:
        date_column = "stat_end" if dataset.scope == "market" else BUSINESS_DAY
        raw = conn.execute(
            f"select count(*) as row_count from {q(table)} where {q(date_column)} = ?",
            (business_day.isoformat(),),
        ).fetchone()
        valid = raw
    if int(valid["row_count"] or 0) > 0:
        return "complete"
    return "partial" if int(raw["row_count"] or 0) > 0 else "missing"


def _latest_day_attempts(
    conn,
    dataset: CollectionDataset,
    *,
    business_day: date,
    store_id: int,
) -> dict[str, str]:
    if not dataset.task_types:
        return {}
    placeholders = ",".join("?" for _ in dataset.task_types)
    rows = conn.execute(
        f"""
        select r.{q(CRAWL_TASK_TYPE)} as task_type,
               d.{q(DAY_STATUS)} as day_status
        from crawl_runs r
        inner join crawl_run_days d on d.{q(CRAWL_RUN_ID)} = r.{q(CRAWL_RUN_ID)}
        where d.{q(STORE_ID)} = ?
          and d.{q(BUSINESS_DAY)} = ?
          and r.{q(CRAWL_TASK_TYPE)} in ({placeholders})
        order by datetime(r.{q(STARTED_AT)}) desc
        """,
        (store_id, business_day.isoformat(), *dataset.task_types),
    ).fetchall()
    attempts: dict[str, str] = {}
    for row in rows:
        task_type = str(row["task_type"])
        if task_type not in attempts:
            attempts[task_type] = str(row["day_status"])
    return attempts


def _has_successful_snapshot_run(
    conn,
    dataset: CollectionDataset,
    *,
    business_day: date,
    store_id: int,
) -> bool:
    if not dataset.task_types:
        return False
    placeholders = ",".join("?" for _ in dataset.task_types)
    rows = conn.execute(
        f"""
        select r.{q(CRAWL_TASK_TYPE)} as task_type, r.{q(RUN_STATUS)} as run_status
        from crawl_runs r
        where r.{q(STORE_ID)} = ?
          and r.{q(CRAWL_TASK_TYPE)} in ({placeholders})
          and r.{q(START_DAY)} <= ?
          and r.{q(END_DAY)} >= ?
        order by datetime(r.{q(STARTED_AT)}) desc
        """,
        (store_id, *dataset.task_types, business_day.isoformat(), business_day.isoformat()),
    ).fetchall()
    latest: dict[str, str] = {}
    for row in rows:
        task_type = str(row["task_type"])
        if task_type not in latest:
            latest[task_type] = str(row["run_status"])
    return all(latest.get(task_type) == "completed" for task_type in dataset.task_types)


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?", (table,)
    ).fetchone() is not None
