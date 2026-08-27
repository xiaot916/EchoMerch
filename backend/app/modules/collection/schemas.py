from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformSessionStatus(BaseModel):
    code: str
    name: str
    status: str
    detail: str
    page_detected: bool = False
    authenticated: bool = False
    cookie_detected: bool = False
    cookie_count: int = 0


class BrowserHealth(BaseModel):
    status: str
    browser_connected: bool = False
    source: str
    debug_port: int
    detail: str
    last_verified_at: str
    platforms: list[PlatformSessionStatus] = Field(default_factory=list)


class InventoryCredentialStatus(BaseModel):
    configured: bool = False
    status: str = "not_configured"
    source: str = "none"
    refresh_token_configured: bool = False
    access_token_configured: bool = False
    access_token_expired: bool = False
    updated_at: str | None = None
    detail: str = "尚未配置吉客云库存凭证。"


class UpdateInventoryCredentialsRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)
    access_token: str | None = Field(default=None, max_length=4096)
    access_token_ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class InventoryCredentialTestResponse(BaseModel):
    status: str
    detail: str
    credential_status: InventoryCredentialStatus


class CollectionSettings(BaseModel):
    session_source: str
    browser_port: int
    cookie_env: str
    mode: str
    safety_rules: list[str] = Field(default_factory=list)
    inventory_credentials: InventoryCredentialStatus = Field(default_factory=InventoryCredentialStatus)


class DatasetTableCoverage(BaseModel):
    table: str
    present: bool
    row_count: int = 0
    raw_row_count: int = 0
    latest_date: str | None = None
    status: str = "missing"


class DatasetCoverage(BaseModel):
    key: str
    label: str
    group: str
    description: str
    collection_mode: str = "daily_fact"
    status: str
    target_day: str
    present_tables: int
    expected_tables: int
    row_count: int
    latest_date: str | None = None
    last_attempt_at: str | None = None
    last_run_status: str | None = None
    error_message: str | None = None
    tables: list[DatasetTableCoverage] = Field(default_factory=list)


class DayCoverage(BaseModel):
    day: str
    complete: int
    no_data: int
    attention: int
    total: int
    coverage_percent: int


class CollectionBatchFailure(BaseModel):
    dataset_key: str
    dataset_label: str
    task_type: str | None = None
    run_id: str | None = None
    status: str
    error_message: str | None = None


class CollectionBatch(BaseModel):
    batch_id: str
    business_day: str
    dataset_names: list[str] = Field(default_factory=list)
    trigger: str
    session_source: str
    refresh_existing: bool = False
    status: str
    process_id: int | None = None
    completed_count: int = 0
    failed_count: int = 0
    started_at: str
    finished_at: str | None = None
    log_file: str
    error_message: str | None = None
    total_count: int = 0
    settled_count: int = 0
    progress_percent: int = 0
    success_rate: float = 0
    current_dataset_key: str | None = None
    current_dataset_label: str | None = None
    current_task_type: str | None = None
    failure_details: list[CollectionBatchFailure] = Field(default_factory=list)


class CollectionSchedule(BaseModel):
    enabled: bool = False
    run_time: str = "07:30"
    timezone: str = "Asia/Shanghai"
    dataset_names: list[str] = Field(default_factory=list)
    session_source: str = "drissionpage"
    last_triggered_day: str | None = None
    last_triggered_at: str | None = None
    next_run_at: str | None = None


class CollectionOverview(BaseModel):
    target_day: str
    generated_at: str
    total_datasets: int
    complete_count: int
    partial_count: int
    missing_count: int
    failed_count: int
    no_data_count: int
    collecting_count: int
    coverage_percent: int
    datasets: list[DatasetCoverage] = Field(default_factory=list)
    recent_days: list[DayCoverage] = Field(default_factory=list)
    latest_batch: CollectionBatch | None = None
    schedule: CollectionSchedule


class StartCollectionRequest(BaseModel):
    day: str | None = None
    dataset_names: list[str] = Field(default_factory=list)
    session_source: str = "drissionpage"
    refresh_existing: bool = False
    # Manual collection uses the same per-dataset catch-up planner as the
    # scheduler. This is important for delayed reports whose first response
    # may contain only a partial metric bundle.
    resume_from_latest: bool = True


class UpdateCollectionScheduleRequest(BaseModel):
    enabled: bool
    run_time: str
    dataset_names: list[str] = Field(default_factory=list)
    session_source: str = "drissionpage"
