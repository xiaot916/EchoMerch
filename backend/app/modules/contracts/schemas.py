from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResponseEvidence(BaseModel):
    files: int = 0
    json_like_files: int = 0
    samples: list[dict[str, Any]] = Field(default_factory=list)
    shape: list[dict[str, Any]] = Field(default_factory=list)


class EndpointContract(BaseModel):
    host: str = ""
    path: str
    method: str = ""
    calls: int = 0
    daily_calls: int = 0
    success_calls: int = 0
    statuses: dict[str, int] = Field(default_factory=dict)
    date_modes: dict[str, int] = Field(default_factory=dict)
    business_dates: dict[str, int] = Field(default_factory=dict)
    sample_params: dict[str, str] = Field(default_factory=dict)
    sample_headers: dict[str, str] = Field(default_factory=dict)
    response: ResponseEvidence = Field(default_factory=ResponseEvidence)


class ContractSummary(BaseModel):
    generated_at: str | None = None
    source: str
    api_observations: int
    endpoint_contracts: int
    daily_observations: int
    business_dates: dict[str, int]
    date_modes: dict[str, int]
    priority_paths: list[EndpointContract] = Field(default_factory=list)


class ContractCatalog(BaseModel):
    generated_at: str | None = None
    contracts: list[EndpointContract] = Field(default_factory=list)
