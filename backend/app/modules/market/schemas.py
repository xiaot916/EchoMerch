from datetime import date, datetime

from pydantic import BaseModel, Field


class MarketCoverage(BaseModel):
    dataset: str
    range_start: date
    range_end: date
    expected_days: int
    covered_days: int
    missing_dates: list[date] = Field(default_factory=list)
    first_date: date | None = None
    latest_date: date | None = None
    latest_fetched_at: datetime | None = None
    status: str = "empty"


class MarketRanking(BaseModel):
    rank_no: int
    rank_change: int | None = None
    rank_type: str
    entity_type: str
    entity_id: str | None = None
    entity_name: str = ""
    shop_name: str | None = None
    keyword: str | None = None
    paid_buyers_range: str | None = None
    visitors_range: str | None = None
    sale_item_count: int | None = None
    content_title: str | None = None
    content_start_time: str | None = None
    fan_count_range: str | None = None
    grass_paid_amount_range: str | None = None
    goods_clicks_range: str | None = None
    live_views_range: str | None = None
    is_monitored: bool = False


class MarketKeyword(BaseModel):
    rank_no: int
    keyword_type: str
    keyword: str = ""
    popularity_range: str | None = None
    click_rate: float | None = None
    pay_conversion_rate: str | None = None
    pay_conversion_midpoint: float | None = None
    opportunity_score: float | None = None
    category_relevance: str = "unclassified"


class MarketDailyMetric(BaseModel):
    stat_date: date
    ranking_rows: int = 0
    shops: int = 0
    items: int = 0
    keywords: int = 0
    average_click_rate: float | None = None
    average_pay_conversion_rate: float | None = None
    high_opportunity_keywords: int = 0
    ranking_risers: int = 0
    ranking_fallers: int = 0


class MarketOpportunity(BaseModel):
    keyword: str
    keyword_type: str
    evidence: str
    action: str
    score: float | None = None


class MarketDemandSignal(BaseModel):
    keyword: str
    keyword_type: str
    current_rank: int
    previous_rank: int | None = None
    rank_change: int | None = None
    direction: str = "stable"
    days_seen: int = 1
    popularity_range: str | None = None
    click_rate: float | None = None
    pay_conversion_midpoint: float | None = None
    opportunity_score: float | None = None
    evidence: str = ""
    action: str = ""
    confidence: str = "medium"


class MarketDecision(BaseModel):
    priority: str
    theme: str
    title: str
    finding: str
    evidence: str
    action: str
    validation: str
    confidence: str = "medium"


class MarketCompetitiveSignal(BaseModel):
    rank_type: str
    entity_id: str | None = None
    name: str
    current_rank: int
    rank_change: int | None = None
    direction: str = "stable"
    evidence: str = ""
    action: str = ""


class MarketKeywordSegment(BaseModel):
    keyword_type: str
    keyword_count: int = 0
    top_keyword: str | None = None
    average_click_rate: float | None = None
    average_pay_conversion_rate: float | None = None
    average_opportunity_score: float | None = None
    high_opportunity_count: int = 0


class MarketSummary(BaseModel):
    ranking_rows: int = 0
    keyword_rows: int = 0
    shop_count: int = 0
    item_count: int = 0
    content_count: int = 0
    keyword_count: int = 0
    latest_rank_date: date | None = None
    latest_keyword_date: date | None = None
    top_shop: str | None = None
    top_item: str | None = None
    top_content: str | None = None
    top_keyword: str | None = None
    monitored_count: int = 0
    relevant_keyword_count: int = 0
    high_opportunity_count: int = 0
    rank_mover_count: int = 0
    coverage_rate: float = 0
    rising_counts: dict[str, int] = Field(default_factory=dict)
    falling_counts: dict[str, int] = Field(default_factory=dict)


class MarketInsightResponse(BaseModel):
    range_start: date
    range_end: date
    latest_available_date: date | None = None
    scope_label: str = "平台市场排行与搜索词"
    summary: MarketSummary
    coverage: list[MarketCoverage] = Field(default_factory=list)
    daily_metrics: list[MarketDailyMetric] = Field(default_factory=list)
    rankings: list[MarketRanking] = Field(default_factory=list)
    keywords: list[MarketKeyword] = Field(default_factory=list)
    opportunities: list[MarketOpportunity] = Field(default_factory=list)
    demand_signals: list[MarketDemandSignal] = Field(default_factory=list)
    decisions: list[MarketDecision] = Field(default_factory=list)
    competitive_signals: list[MarketCompetitiveSignal] = Field(default_factory=list)
    keyword_segments: list[MarketKeywordSegment] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    data_quality_flags: list[str] = Field(default_factory=list)
