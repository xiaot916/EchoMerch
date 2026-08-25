from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewCollectRequest(BaseModel):
    mode: str = Field(default="incremental", pattern="^(initial|incremental)$")
    max_pages: int = Field(default=1000, ge=1, le=5000)
    # 淘宝评价接口不带日期时会在约 5,000 条处截断；初次采集默认覆盖
    # 2025-01-01 至今，并由服务按月切片请求。
    start_date: str = Field(default="2025-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class AskCollectRequest(BaseModel):
    mode: str = Field(default="incremental", pattern="^(initial|incremental)$")
    max_pages: int = Field(default=500, ge=1, le=1000)


class ReviewCollectionRun(BaseModel):
    run_id: str
    mode: str
    status: str
    started_at: str
    finished_at: str | None = None
    pages: int = 0
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    stopped_reason: str | None = None
    error: str | None = None


class ReviewCollectionSummary(BaseModel):
    total_reviews: int = 0
    first_review_date: str | None = None
    latest_review_date: str | None = None
    last_collected_at: str | None = None
    last_run: ReviewCollectionRun | None = None
    product_count: int = 0
    series_count: int = 0


class ReviewRecord(BaseModel):
    review_key: str
    platform_review_id: str | None = None
    user_name: str | None = None
    security_id: str | None = None
    emotion_type: str | None = None
    order_id: str | None = None
    item_id: str | None = None
    item_name: str | None = None
    item_link: str | None = None
    series: str | None = None
    review_date: str | None = None
    main_content: str = ""
    append_content: str = ""
    merged_content: str = ""
    main_media: list[str] = Field(default_factory=list)
    append_media: list[str] = Field(default_factory=list)
    overview: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    is_negative: bool = True
    sentiment: str = "unknown"
    fetched_at: str | None = None


class ReviewCategoryCount(BaseModel):
    name: str
    count: int
    share: float


class ReviewTrendPoint(BaseModel):
    day: str
    total: int
    negative: int


class ReviewRiskMetric(BaseModel):
    key: str
    label: str
    series: str | None = None
    total_reviews: int = 0
    issue_reviews: int = 0
    issue_rate: float = 0
    top_issue: str | None = None


class ReviewAnalysis(BaseModel):
    scope: str = "all"
    product_id: str | None = None
    series: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    total_reviews: int = 0
    negative_reviews: int = 0
    normal_reviews: int = 0
    negative_rate: float = 0
    append_reviews: int = 0
    media_reviews: int = 0
    product_count: int = 0
    category_counts: list[ReviewCategoryCount] = Field(default_factory=list)
    competitor_counts: list[ReviewCategoryCount] = Field(default_factory=list)
    trend: list[ReviewTrendPoint] = Field(default_factory=list)
    risk_products: list[ReviewRiskMetric] = Field(default_factory=list)
    risk_series: list[ReviewRiskMetric] = Field(default_factory=list)
    top_reviews: list[ReviewRecord] = Field(default_factory=list)


class ReviewListResponse(BaseModel):
    items: list[ReviewRecord] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class AskRecord(BaseModel):
    ask_id: str
    item_id: str | None = None
    item_name: str | None = None
    item_link: str | None = None
    series: str | None = None
    user_name: str | None = None
    question: str = ""
    question_date: str | None = None
    answer_count: int = 0
    has_answer: bool = False
    categories: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    fetched_at: str | None = None


class AskListResponse(BaseModel):
    items: list[AskRecord] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class AskSummary(BaseModel):
    total_questions: int = 0
    answered_questions: int = 0
    unanswered_questions: int = 0
    answer_rate: float = 0
    product_count: int = 0
    first_question_date: str | None = None
    latest_question_date: str | None = None
    category_counts: list[ReviewCategoryCount] = Field(default_factory=list)
    last_run: ReviewCollectionRun | None = None
