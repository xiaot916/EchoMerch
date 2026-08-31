from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


AnalysisStatus = Literal["ok", "partial", "no_data", "error"]
AIDomain = Literal[
    "auto", "overview", "traffic", "promotion", "market", "inventory", "budget", "planning",
    "product", "customer", "customer-service", "content", "live", "campaign", "reviews",
]


class AnalysisContext(BaseModel):
    store_id: int | None = None
    range_start: date
    range_end: date
    timezone: str = "Asia/Shanghai"
    filters: dict[str, Any] = Field(default_factory=dict)


class MetricValue(BaseModel):
    id: str
    label: str
    value: float | int | None
    unit: str = ""
    formula: str = ""
    comparison: dict[str, float | int | None] = Field(default_factory=dict)
    source: str = ""


class CoverageSummary(BaseModel):
    expected_days: int = 0
    covered_days: int = 0
    missing_dates: list[str] = Field(default_factory=list)
    missing_datasets: list[str] = Field(default_factory=list)
    partial_datasets: list[str] = Field(default_factory=list)
    failed_datasets: list[str] = Field(default_factory=list)
    no_data_datasets: list[str] = Field(default_factory=list)
    no_data_dates: list[str] = Field(default_factory=list)
    latest_data_date: str | None = None


class EvidenceRecord(BaseModel):
    dataset: str
    table: str = ""
    date_range: list[str] = Field(default_factory=list)
    row_count: int = 0
    note: str = ""
    fields: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)
    lineage: str = ""


class MCPEnvelope(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    tool: str
    generated_at: str
    context: AnalysisContext
    status: AnalysisStatus
    data: dict[str, Any] = Field(default_factory=dict)
    metrics: list[MetricValue] = Field(default_factory=list)
    coverage: CoverageSummary = Field(default_factory=CoverageSummary)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class MCPExecuteRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class SkillToolStep(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class SkillDescriptor(BaseModel):
    name: str
    display_name: str
    description: str
    version: str
    domains: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    workflow: list[SkillToolStep] = Field(default_factory=list)
    enabled: bool = True


class DiagnosisFinding(BaseModel):
    level: Literal["critical", "warning", "positive", "info"] = "info"
    title: str
    detail: str
    metric_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    impact: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class RecommendedAction(BaseModel):
    priority: Literal["P0", "P1", "P2"] = "P1"
    title: str
    detail: str
    owner: str = "运营"
    validation: str = ""
    observation_window: str = ""
    expected_impact: str = ""
    object_type: str = ""
    object_id: str = ""
    problem: str = ""
    verify_metric: str = ""
    stop_condition: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class ArtifactSpec(BaseModel):
    type: Literal["metric_table", "bar_chart", "line_chart", "matrix"]
    title: str
    columns: list[dict[str, str]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    option: dict[str, Any] = Field(default_factory=dict)


class Diagnosis(BaseModel):
    headline: str
    summary: str
    findings: list[DiagnosisFinding] = Field(default_factory=list)
    actions: list[RecommendedAction] = Field(default_factory=list)
    artifacts: list[ArtifactSpec] = Field(default_factory=list)
    # Stable analysis contract consumed by the model, API clients and UI.
    analysis_scope: dict[str, Any] = Field(default_factory=dict)
    coverage: CoverageSummary = Field(default_factory=CoverageSummary)
    confidence: Literal["high", "medium", "low"] = "medium"
    assumptions: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    metric_definitions: dict[str, str] = Field(default_factory=dict)
    denominator_notes: list[str] = Field(default_factory=list)
    causal_boundary: str = ""
    next_questions: list[str] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, min_length=8, max_length=120)
    store_id: int | None = Field(default=None, ge=1)
    start_date: date | None = None
    end_date: date | None = None
    domain: AIDomain = "auto"
    page_key: str | None = Field(default=None, min_length=1, max_length=80)
    page_context: dict[str, Any] = Field(default_factory=dict)
    use_model: bool = True


class PageAIProfileDescriptor(BaseModel):
    key: str
    title: str
    section: str
    domain: AIDomain
    primary_skill: str
    goal: str
    diagnostic_question: str
    data_domains: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    recommended_questions: list[str] = Field(default_factory=list)
    focus_dimensions: list[str] = Field(default_factory=list)
    decision_lens: dict[str, str] = Field(default_factory=dict)
    quality_checks: list[str] = Field(default_factory=list)


class PeriodReportRequest(BaseModel):
    report_type: Literal["daily", "weekly", "monthly", "mtd", "daily_series"] = "daily"
    conversation_id: str | None = Field(default=None, min_length=8, max_length=120)
    anchor_date: date | None = None
    store_id: int | None = Field(default=None, ge=1)
    target_gmv: float | None = Field(default=None, ge=0)
    use_model: bool = True


class PeriodReportResponse(BaseModel):
    request_id: str
    conversation_id: str | None = None
    status: AnalysisStatus
    report_type: str
    range_start: date
    range_end: date
    title: str
    text: str
    report: dict[str, Any] = Field(default_factory=dict)
    diagnosis: Diagnosis
    mcp_result: MCPEnvelope
    skill: SkillDescriptor
    provider: str = "rules"
    model: str | None = None
    elapsed_ms: float | None = None
    execution_steps: list["ExecutionStep"] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExecutionStep(BaseModel):
    kind: Literal["planner", "skill", "mcp", "model"]
    name: str
    status: Literal["completed", "skipped", "failed"]
    detail: str = ""
    elapsed_ms: float | None = None


class AnalysisResponse(BaseModel):
    request_id: str
    conversation_id: str | None = None
    status: AnalysisStatus
    skill: SkillDescriptor
    supporting_skills: list[SkillDescriptor] = Field(default_factory=list)
    provider: str
    model: str | None = None
    elapsed_ms: float | None = None
    answer: str
    diagnosis: Diagnosis
    mcp_results: list[MCPEnvelope] = Field(default_factory=list)
    conversation_memory: dict[str, Any] = Field(default_factory=dict)
    execution_steps: list[ExecutionStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AIHealthResponse(BaseModel):
    status: Literal["configured", "not_configured"]
    provider: str
    model: str
    endpoint: str
    api_key_configured: bool


class AIConfigurationResponse(BaseModel):
    base_url: str
    api_path: str
    endpoint: str
    model: str
    timeout_seconds: float
    api_key_configured: bool
    api_key_masked: str | None = None


class AIConfigurationUpdate(BaseModel):
    base_url: str = Field(min_length=1, max_length=500)
    api_path: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    timeout_seconds: float = Field(default=45, ge=1, le=300)
    api_key: str | None = Field(default=None, max_length=500)


class AIConnectionTestResponse(BaseModel):
    ok: bool
    model: str
    status_code: int | None = None
    elapsed_ms: float | None = None
    reply: str = ""
    error: str | None = None


class AIConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    created_at: str
    payload: dict[str, Any] | None = None


class AIConversationState(BaseModel):
    conversation_id: str
    summary: str = ""
    memory: dict[str, Any] = Field(default_factory=dict)
    recent_messages: list[AIConversationMessage] = Field(default_factory=list)
    updated_at: str | None = None


class AIConversationListItem(BaseModel):
    conversation_id: str
    title: str
    updated_at: str
    message_count: int = 0


class AIConversationDetail(AIConversationState):
    title: str = "新对话"


class MCPToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPQueryRequest(BaseModel):
    """Structured, read-only query request accepted by the generic data MCP."""

    dataset: str = Field(min_length=1, max_length=80)
    dimensions: list[str] = Field(default_factory=list, max_length=8)
    measures: list[str] = Field(default_factory=list, max_length=20)
    filters: dict[str, Any] = Field(default_factory=dict)
    order_by: list[str] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=100, ge=1, le=1000)
    start_date: date | None = None
    end_date: date | None = None
    store_id: int | None = Field(default=None, ge=1)
    history_scope: Literal["selected", "all"] = "selected"


class MCPCompareRequest(MCPQueryRequest):
    """Query a period and its immediately preceding equal-length period."""

    pass


class DatasetField(BaseModel):
    id: str
    label: str
    column: str
    kind: Literal["dimension", "measure"]
    unit: str = ""
    aggregation: str = "sum"
    description: str = ""
    formula: str = ""


class DatasetDescriptor(BaseModel):
    key: str
    label: str
    table: str
    grain: str
    date_column: str
    dimensions: list[DatasetField] = Field(default_factory=list)
    measures: list[DatasetField] = Field(default_factory=list)
    coverage_supported: bool = True


class MCPQueryResult(BaseModel):
    dataset: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    aggregates: dict[str, Any] = Field(default_factory=dict)
    formula: dict[str, str] = Field(default_factory=dict)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    coverage: CoverageSummary = Field(default_factory=CoverageSummary)
