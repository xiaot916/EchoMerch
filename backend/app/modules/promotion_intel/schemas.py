from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, Field


class PlanStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    ROLLED_BACK = "rolled_back"
    CLOSED = "closed"


class PlanSource(str, Enum):
    RULE = "rule"
    AI = "ai"
    MANUAL = "manual"


class TargetType(str, Enum):
    WORD = "word"
    CROWD = "crowd"
    CAMPAIGN = "campaign"
    BUDGET = "budget"
    BIDWORD_PACKAGE = "bidword_package"
    DMP_CROWD = "dmp_crowd"


class ActionType(str, Enum):
    ADJUST_PRICE = "adjust_price"
    ADJUST_PREMIUM = "adjust_premium"
    ADJUST_BUDGET = "adjust_budget"
    PAUSE = "pause"
    RESUME = "resume"
    CHANGE_MATCH = "change_match"
    CHANGE_PERIOD = "change_period"
    BIND_CROWD = "bind_crowd"
    UNBIND_CROWD = "unbind_crowd"
    ADJUST_WORD_PACKAGE = "adjust_word_package"
    DMP_PUSH_CHANNEL = "dmp_push_channel"
    DMP_EXTEND_VALIDITY = "dmp_extend_validity"


class ItemStatus(str, Enum):
    PENDING = "pending"
    PREVIEWED = "previewed"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ExecutionChannel(str, Enum):
    ONEBP_WRITE = "onebp_write"
    DMP_WRITE = "dmp_write"
    UI_MANUAL = "ui_manual"
    ALIMAMA_API = "alimama_api"


class PlanItem(BaseModel):
    """一行 = 一个具体优化操作。"""
    item_id: str
    plan_id: str
    target_type: TargetType
    target_id: str
    target_name: str = ""
    scene: str = ""  # onebpSearch / onebpDisplay / onebpSite / onebpLive / onebpShortVideo
    campaign_id: str = ""
    adgroup_id: str = ""
    action: ActionType
    before_value: str = ""
    after_value: str = ""
    reason: str = ""
    channel: ExecutionChannel = ExecutionChannel.ONEBP_WRITE
    status: ItemStatus = ItemStatus.PENDING
    error: str = ""
    executed_at: str = ""


class OptimizationPlan(BaseModel):
    """一行 = 一次优化批次。"""
    plan_id: str
    batch_name: str
    source: PlanSource
    status: PlanStatus
    generated_at: datetime
    generated_by: str = "system"
    window_days: int = 30  # 诊断所用的回溯窗口
    baseline: dict[str, float] = Field(default_factory=dict)  # 保本ROI/实际CPC/ROI/客单等
    items: list[PlanItem] = Field(default_factory=list)
    rollback_snapshot: str = ""  # JSON 字符串，回滚依据
    executed_at: str = ""
    notes: str = ""


class Snapshot(BaseModel):
    """一次快照（回滚基线）。"""
    plan_id: str
    created_at: datetime
    campaigns: list[dict] = Field(default_factory=list)
    words: list[dict] = Field(default_factory=list)
    crowds: list[dict] = Field(default_factory=list)
    budgets: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ReviewVerdict(str, Enum):
    PAUSE_NEW = "pause_new"
    HOLD = "hold"
    SCALE_UP = "scale_up"
    NO_DATA = "no_data"


class ReviewRun(BaseModel):
    """一次 T+7 复盘。"""
    plan_id: str
    review_day: date
    window_days: int = 7
    cvr: float = 0.0
    roi: float = 0.0
    break_even_roi: float = 2.5
    verdict: ReviewVerdict = ReviewVerdict.NO_DATA
    action_taken: str = ""
    executed_at: str = ""
    notes: str = ""
