from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.core.local_database import LocalDatabase
from app.modules.imports.schemas import (
    DailyDryRunSummary,
    ImportGuardrails,
    ImportRun,
    ImportRunDetail,
    ImportRunItem,
    ImportRunList,
)
from app.modules.imports.service import ImportPlanService


class ImportRunMissing(RuntimeError):
    pass


class ImportRunStore:
    def __init__(self, database_path: Path, plan_service: ImportPlanService) -> None:
        self.database_path = database_path
        self.plan_service = plan_service
        self._database = LocalDatabase(database_path)

    def create_from_dry_run(self, day: str | None, idempotency_key: str | None) -> ImportRunDetail:
        plan = self.plan_service.get_latest_or_day(day)
        fingerprint = self._plan_fingerprint(plan)
        run_id = f"dry_{plan.day.replace('-', '')}_{fingerprint}"
        next_idempotency_key = idempotency_key or f"daily-dry-run:{plan.day}:{fingerprint}"

        with self._connect(initialize=True) as conn:
            existing = conn.execute(
                'select "运行ID" as run_id from import_runs where "幂等键" = ?',
                (next_idempotency_key,),
            ).fetchone()
            if existing:
                return self.get_detail(existing["run_id"], conn=conn)

            now = self._now()
            item_statuses = [self._item_status(item.shape_status) for item in plan.selected]
            status = "needs_mapping" if "needs_mapping" in item_statuses else "preview_ready"
            conn.execute(
                """
                insert into import_runs (
                    "运行ID", "幂等键", "业务日期", "运行模式", "运行状态",
                    "来源脚本", "生成时间", "创建时间", "更新时间",
                    "选中数量", "延后数量", "安全规则JSON"
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    next_idempotency_key,
                    plan.day,
                    plan.mode,
                    status,
                    plan.source,
                    plan.generated_at,
                    now,
                    now,
                    len(plan.selected),
                    len(plan.deferred),
                    self._json(plan.guardrails.model_dump()),
                ),
            )
            for index, item in enumerate(plan.selected, start=1):
                contract = item.request_contract
                item_status = self._item_status(item.shape_status)
                conn.execute(
                    """
                    insert into import_run_items (
                        "运行ID", "条目顺序", "函数名称", "优先级", "旧接口路径",
                        "请求方法", "请求地址", "目标表", "日期模式", "响应形状状态",
                        "运行时凭证JSON", "查询参数JSON", "请求体JSON",
                        "条目状态", "风险提示JSON"
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        index,
                        item.function,
                        item.priority,
                        item.legacy_path,
                        contract.method,
                        contract.url,
                        contract.target_table,
                        item.date_mode,
                        item.shape_status,
                        self._json(contract.runtime_credentials),
                        self._json(contract.query_params),
                        self._json(contract.body_template),
                        item_status,
                        self._json(self._risk_notes(item.shape_status, contract.runtime_credentials)),
                    ),
                )
            conn.commit()
            return self.get_detail(run_id, conn=conn)

    def list_runs(self, limit: int = 20) -> ImportRunList:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select "运行ID" as run_id, "业务日期" as day, "运行模式" as mode,
                       "运行状态" as status, "来源脚本" as source,
                       "生成时间" as generated_at, "创建时间" as created_at,
                       "更新时间" as updated_at, "选中数量" as selected_count,
                       "延后数量" as deferred_count, "安全规则JSON" as guardrails_json
                from import_runs
                order by datetime("创建时间") desc
                limit ?
                """,
                (limit,),
            ).fetchall()
            return ImportRunList(runs=[self._run_from_row(row) for row in rows])

    def get_detail(self, run_id: str, conn: sqlite3.Connection | None = None) -> ImportRunDetail:
        if conn is not None:
            return self._get_detail(run_id, conn)
        with self._connect() as next_conn:
            return self._get_detail(run_id, next_conn)

    def _get_detail(self, run_id: str, conn: sqlite3.Connection) -> ImportRunDetail:
        row = conn.execute(
            """
            select "运行ID" as run_id, "业务日期" as day, "运行模式" as mode,
                   "运行状态" as status, "来源脚本" as source,
                   "生成时间" as generated_at, "创建时间" as created_at,
                   "更新时间" as updated_at, "选中数量" as selected_count,
                   "延后数量" as deferred_count, "安全规则JSON" as guardrails_json
            from import_runs
            where "运行ID" = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise ImportRunMissing(f"Import run not found: {run_id}")
        item_rows = conn.execute(
            """
            select "条目ID" as item_id, "运行ID" as run_id, "条目顺序" as item_order,
                   "函数名称" as function_name, "优先级" as priority,
                   "旧接口路径" as legacy_path, "请求方法" as method,
                   "请求地址" as url, "目标表" as target_table,
                   "日期模式" as date_mode, "响应形状状态" as shape_status,
                   "运行时凭证JSON" as runtime_credentials_json,
                   "查询参数JSON" as query_params_json, "请求体JSON" as body_template_json,
                   "条目状态" as status, "风险提示JSON" as risk_notes_json
            from import_run_items
            where "运行ID" = ?
            order by "条目顺序" asc
            """,
            (run_id,),
        ).fetchall()
        return ImportRunDetail(
            **self._run_from_row(row).model_dump(),
            items=[self._item_from_row(item_row) for item_row in item_rows],
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
    def _plan_fingerprint(plan: DailyDryRunSummary) -> str:
        payload = json.dumps(
            plan.model_dump(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _item_status(shape_status: str) -> str:
        if "unconfirmed" in shape_status or "without_json_metric_body" in shape_status:
            return "needs_mapping"
        return "preview_ready"

    @staticmethod
    def _risk_notes(shape_status: str, runtime_credentials: list[str]) -> list[str]:
        notes = ["platform_replay_disabled", "mysql_write_disabled"]
        if runtime_credentials:
            notes.append("runtime_credentials_required")
        if "unconfirmed" in shape_status or "without_json_metric_body" in shape_status:
            notes.append("parser_mapping_required")
        return notes

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> ImportRun:
        return ImportRun(
            run_id=row["run_id"],
            day=row["day"],
            mode=row["mode"],
            status=row["status"],
            source=row["source"],
            generated_at=row["generated_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            selected_count=row["selected_count"],
            deferred_count=row["deferred_count"],
            guardrails=ImportGuardrails.model_validate(json.loads(row["guardrails_json"])),
        )

    @staticmethod
    def _item_from_row(row: sqlite3.Row) -> ImportRunItem:
        return ImportRunItem(
            item_id=row["item_id"],
            run_id=row["run_id"],
            item_order=row["item_order"],
            function_name=row["function_name"],
            priority=row["priority"],
            legacy_path=row["legacy_path"],
            method=row["method"],
            url=row["url"],
            target_table=row["target_table"],
            date_mode=row["date_mode"],
            shape_status=row["shape_status"],
            runtime_credentials=json.loads(row["runtime_credentials_json"]),
            query_params=json.loads(row["query_params_json"]),
            body_template=json.loads(row["body_template_json"])
            if row["body_template_json"]
            else None,
            status=row["status"],
            risk_notes=json.loads(row["risk_notes_json"]),
        )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
