from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class StoreDataColumn(BaseModel):
    key: str
    label: str


class StoreDataDataset(BaseModel):
    key: str
    label: str
    description: str
    row_count: int = 0
    first_date: date | None = None
    latest_date: date | None = None
    status: str = "empty"
    lag_days: int | None = None
    columns: list[StoreDataColumn] = Field(default_factory=list)


class StoreDataCatalog(BaseModel):
    store_id: int
    reference_date: date | None = None
    available_count: int = 0
    current_count: int = 0
    stale_count: int = 0
    empty_count: int = 0
    datasets: list[StoreDataDataset] = Field(default_factory=list)


class StoreDataPreview(BaseModel):
    dataset: dict[str, str]
    store_id: int
    start_date: date | None = None
    end_date: date | None = None
    page: int
    page_size: int
    total: int
    columns: list[StoreDataColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
