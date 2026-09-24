from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.modules.promotion_intel.diagnosis import DiagnosisInput, PromotionDiagnoser
from app.modules.promotion_intel.executor import PlanExecutor
from app.modules.promotion_intel.review import ReviewTracker
from app.modules.promotion_intel.schemas import OptimizationPlan, ReviewRun
from app.modules.promotion_intel.strategy import StrategyEngine

router = APIRouter(prefix="/promotion-intel", tags=["promotion-intel"])


class BaselineIn(BaseModel):
    break_even_roi: float = 2.5
    actual_cpc: float = 1.085
    actual_roi: float = 2.883
    customer_unit_price: float = 90.12
    gross_margin: float = 0.65
    baseline_cvr: float = 0.05


class DiagnoseIn(BaseModel):
    campaigns: list[dict] = []
    crowds: list[dict] = []
    words: list[dict] = []
    word_packages: list[dict] = []
    daily_overview: dict = {}
    baseline: BaselineIn = BaselineIn()


class PlanOut(BaseModel):
    plan: OptimizationPlan


@router.post("/diagnose")
def diagnose(body: DiagnoseIn):
    """跑 6 条硬规则诊断，返回 Finding 列表。"""
    diagnoser = PromotionDiagnoser(body.baseline.model_dump())
    data = DiagnosisInput(
        campaigns=body.campaigns,
        crowds=body.crowds,
        words=body.words,
        word_packages=body.word_packages,
        daily_overview=body.daily_overview,
        baseline=body.baseline.model_dump(),
    )
    findings = diagnoser.run(data)
    return {"findings": [
        {"code": f.code, "severity": f.severity, "title": f.title,
         "detail": f.detail, "targets": list(f.targets)}
        for f in findings
    ]}


@router.post("/plan")
def build_plan(body: DiagnoseIn, batch_name: str = Query(default="unnamed")):
    """诊断 + 策略 → OptimizationPlan（draft 状态）。"""
    diagnoser = PromotionDiagnoser(body.baseline.model_dump())
    data = DiagnosisInput(
        campaigns=body.campaigns,
        crowds=body.crowds,
        words=body.words,
        word_packages=body.word_packages,
        daily_overview=body.daily_overview,
        baseline=body.baseline.model_dump(),
    )
    findings = diagnoser.run(data)
    engine = StrategyEngine(body.baseline.model_dump())
    plan = engine.build_plan(batch_name, data, findings)
    return PlanOut(plan=plan).model_dump()


@router.post("/review")
def review_plan(body: dict):
    """T+7 复盘。body: {plan, metrics:{cvr,roi,charge,gmv}, review_day?}"""
    plan = OptimizationPlan.model_validate(body.get("plan") or {})
    baseline = body.get("baseline") or {"break_even_roi": 2.5}
    tracker = ReviewTracker(baseline)
    run = tracker.review(plan, body.get("metrics") or {}, review_day=body.get("review_day"))
    return run.model_dump()
