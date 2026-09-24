from __future__ import annotations

from pydantic import BaseModel, Field


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
