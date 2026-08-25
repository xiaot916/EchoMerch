from datetime import date, datetime

from pydantic import BaseModel


class CaptureFamilySummary(BaseModel):
    family: str
    observations: int


class DailyRequestSummary(BaseModel):
    business_date: date | None
    date_mode: str
    files: int


class CaptureSummary(BaseModel):
    file_count: int
    first_date: date | None
    last_date: date | None
    imported_at: datetime | None
    families: list[CaptureFamilySummary]
    daily_requests: list[DailyRequestSummary] = []
