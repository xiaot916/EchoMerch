from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OperationCapability(BaseModel):
    key: str
    title: str
    status: Literal["enabled", "dry_run_only", "disabled", "planned"]
    risk_level: Literal["low", "medium", "high"]
    mode: str
    guardrails: list[str] = Field(default_factory=list)


class OperationCenterSummary(BaseModel):
    mode: Literal["read_only", "dry_run_only"]
    capabilities: list[OperationCapability]
    required_flow: list[str]

