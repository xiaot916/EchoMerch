from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.modules.promotion_intel.schemas import (
    OptimizationPlan,
    ReviewRun,
    ReviewVerdict,
)


class ReviewTracker:
    """T+7 复盘追踪器。

    判定矩阵：
      CVR < 2%           → 暂停拉新计划（止血）
      CVR ≥ 2% & ROI < 保本 → 维持 7 天再判
      CVR ≥ 2% & ROI ≥ 保本 → 回加预算 25~30%
      无数据             → NO_DATA（不触发任何动作）

    调用方负责：
    1. 从 store_daily_promotion_campaigns 拉 plan 执行后 T+7 的 7 日切片
    2. 把切片喂给 review()，拿到 ReviewRun
    3. 台账写入《优化过程记录.xlsx》01_优化台账 sheet（表头第 3 行）
    4. 判定为暂停时调 PlanExecutor.rollback 反向操作
    """

    CVR_THRESHOLD = 0.02  # 2%
    BUDGET_SCALE_RATIO = 1.25  # 回加 25%

    def __init__(self, baseline: dict[str, float]) -> None:
        self.baseline = baseline
        self.break_even_roi = float(baseline.get("break_even_roi") or 2.5)

    def review(
        self,
        plan: OptimizationPlan,
        metrics: dict[str, Any],
        *,
        review_day: date | None = None,
        window_days: int = 7,
    ) -> ReviewRun:
        """输入 plan + 7 日切片指标，返回 ReviewRun。

        metrics 字段约定：
          - cvr: 7 日支付转化率（小数）
          - roi: 7 日 ROI（倍数）
          - charge: 7 日花费
          - gmv: 7 日归因成交
        """
        review_day = review_day or date.today()
        cvr = float(metrics.get("cvr") or 0)
        roi = float(metrics.get("roi") or 0)

        if cvr <= 0 and roi <= 0:
            verdict = ReviewVerdict.NO_DATA
            action = ""
        elif cvr < self.CVR_THRESHOLD:
            verdict = ReviewVerdict.PAUSE_NEW
            action = "CVR 未过 2%，拉新计划暂停止血"
        elif roi < self.break_even_roi:
            verdict = ReviewVerdict.HOLD
            action = "ROI 未过保本线，维持 7 天再判"
        else:
            verdict = ReviewVerdict.SCALE_UP
            action = f"ROI {roi:.2f} ≥ 保本 {self.break_even_roi}，回加预算 {self.BUDGET_SCALE_RATIO:.0%}"

        return ReviewRun(
            plan_id=plan.plan_id,
            review_day=review_day,
            window_days=window_days,
            cvr=cvr,
            roi=roi,
            break_even_roi=self.break_even_roi,
            verdict=verdict,
            action_taken=action,
            executed_at=datetime.now().isoformat() if verdict != ReviewVerdict.NO_DATA else "",
        )

    def should_rollback(self, run: ReviewRun) -> bool:
        """是否需要触发回滚（仅暂停止血时）。"""
        return run.verdict == ReviewVerdict.PAUSE_NEW

    # ---- 台账行（对齐《33-优化过程记录与汇报.xlsx》01_优化台账） ----
    def ledger_row(self, plan: OptimizationPlan, run: ReviewRun) -> dict[str, Any]:
        """生成一行台账数据（调用方负责追加到 xlsx，表头第 3 行）。"""
        return {
            "复盘日期": run.review_day.isoformat(),
            "计划批次": plan.batch_name,
            "复盘窗口": f"T+{run.window_days}",
            "CVR": f"{run.cvr * 100:.2f}%",
            "ROI": f"{run.roi:.2f}",
            "保本线": f"{run.break_even_roi:.2f}",
            "判定": run.verdict.value,
            "动作": run.action_taken,
            "执行时间": run.executed_at,
            "备注": plan.notes,
        }
