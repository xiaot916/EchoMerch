from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ImportGuardrails(BaseModel):
    platform_requests_executed: int = 0
    mysql_writes: int = 0
    sqlite_connection: str = ""
    raw_cookies_or_tokens_persisted: bool = False


class ImportRequestContract(BaseModel):
    method: str
    url: str
    query_params: dict[str, Any] = Field(default_factory=dict)
    body_template: dict[str, Any] | None = None
    runtime_credentials: list[str] = Field(default_factory=list)
    target_table: str
    execute: bool = False
    write_database: bool = False


class ImportCandidate(BaseModel):
    function: str
    line: int | None = None
    priority: str
    legacy_path: str
    date_mode: str
    shape_status: str
    request_contract: ImportRequestContract


class DeferredImportCandidate(BaseModel):
    function: str
    priority: str
    legacy_path: str
    reason: str


class DailyDryRunSummary(BaseModel):
    generated_at: str | None = None
    mode: str
    day: str
    timezone: str
    source: str
    capture_db: str
    guardrails: ImportGuardrails
    selected_priorities: list[str] = Field(default_factory=list)
    selected: list[ImportCandidate] = Field(default_factory=list)
    deferred: list[DeferredImportCandidate] = Field(default_factory=list)


class CreateImportRunRequest(BaseModel):
    day: str | None = None
    idempotency_key: str | None = None


class ImportRun(BaseModel):
    run_id: str
    day: str
    mode: str
    status: str
    source: str
    generated_at: str | None = None
    created_at: str
    updated_at: str
    selected_count: int
    deferred_count: int
    guardrails: ImportGuardrails


class ImportRunItem(BaseModel):
    item_id: int
    run_id: str
    item_order: int
    function_name: str
    priority: str
    legacy_path: str
    method: str
    url: str
    target_table: str
    date_mode: str
    shape_status: str
    runtime_credentials: list[str] = Field(default_factory=list)
    query_params: dict[str, Any] = Field(default_factory=dict)
    body_template: dict[str, Any] | None = None
    status: str
    risk_notes: list[str] = Field(default_factory=list)


class ImportRunDetail(ImportRun):
    items: list[ImportRunItem] = Field(default_factory=list)


class ImportRunList(BaseModel):
    runs: list[ImportRun] = Field(default_factory=list)


class CrawlRunDay(BaseModel):
    item_id: int
    run_id: str
    store_id: int
    business_day: str
    status: str
    metric_count: int | None = None
    error_message: str | None = None


class CrawlRun(BaseModel):
    run_id: str
    store_id: int
    task_type: str
    start_day: str
    end_day: str
    mode: str
    status: str
    planned_days: int
    success_days: int
    skipped_days: int
    failed_days: int
    started_at: str
    finished_at: str | None = None
    log_file: str


class CrawlRunDetail(CrawlRun):
    days: list[CrawlRunDay] = Field(default_factory=list)


class CrawlRunList(BaseModel):
    runs: list[CrawlRun] = Field(default_factory=list)
