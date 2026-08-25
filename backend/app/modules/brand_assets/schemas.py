from __future__ import annotations

from pydantic import BaseModel, Field


class BrandRecord(BaseModel):
    brand_id: str
    brand_subject_id: str
    brand_name: str
    status: str
    store_ids: list[int] = Field(default_factory=list)


class BrandDatasetStatus(BaseModel):
    key: str
    label: str
    table: str
    row_count: int
    min_day: str | None = None
    max_day: str | None = None
    imported: bool


class BrandProductRecord(BaseModel):
    brand_id: str
    product_id: str
    spu_id: str | None = None
    product_name: str
    series: str | None = None
    category: str | None = None
    product_line: str | None = None
    positioning: str | None = None
    status: str
    launch_date: str | None = None
    row_count: int = 0
    min_day: str | None = None
    max_day: str | None = None


class BrandProductAnalysis(BaseModel):
    brand: BrandRecord
    product: BrandProductRecord
    start_date: str | None = None
    end_date: str | None = None
    latest_day: str | None = None
    data_status: str
    latest_metrics: dict[str, str | None] = Field(default_factory=dict)
    period_metrics: dict[str, float] = Field(default_factory=dict)
    trend: list[dict[str, str | None]] = Field(default_factory=list)
    dimensions: list[dict[str, str | float | None]] = Field(default_factory=list)
    peers: list[dict[str, str | float | None]] = Field(default_factory=list)


class BrandAssetSummary(BaseModel):
    brand: BrandRecord
    start_date: str | None = None
    end_date: str | None = None
    latest_day: str | None = None
    data_status: str
    overview: dict[str, str | None] = Field(default_factory=dict)
    overview_trend: list[dict[str, str | None]] = Field(default_factory=list)
    stages: list[dict[str, str | None]] = Field(default_factory=list)
    dimensions: list[dict[str, str | None]] = Field(default_factory=list)
    metrics: list[dict[str, str | None]] = Field(default_factory=list)
    datasets: list[BrandDatasetStatus] = Field(default_factory=list)
