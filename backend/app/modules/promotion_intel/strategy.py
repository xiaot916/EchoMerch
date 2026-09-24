from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.modules.promotion_intel.diagnosis import DiagnosisInput, Finding
from app.modules.promotion_intel.schemas import (
    ActionType,
    ExecutionChannel,
    ItemStatus,
    OptimizationPlan,
    PlanSource,
    PlanStatus,
    TargetType,
    PlanItem,
)


class StrategyEngine:
    """诊断 Finding → OptimizationPlan 转换器。

    内置公式：
      保本CPC = 客单 × 毛利率 × CVR
      建议溢价% = (1 + 当前%) × 目标CPC / 实际CPC − 1   （clamp 5~500）
      预算弹性权重 = 1 + (roi / break_even_roi − 1) × 0.5
    """

    def __init__(self, baseline: dict[str, float], source: PlanSource = PlanSource.RULE) -> None:
        self.baseline = baseline
        self.source = source

    def build_plan(
        self,
        batch_name: str,
        input_data: DiagnosisInput,
        findings: list[Finding],
    ) -> OptimizationPlan:
        plan_id = f"plan-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        items: list[PlanItem] = []

        for finding in findings:
            items.extend(self._expand_finding(plan_id, finding))

        return OptimizationPlan(
            plan_id=plan_id,
            batch_name=batch_name,
            source=self.source,
            status=PlanStatus.DRAFT,
            generated_at=datetime.now(),
            baseline=self.baseline,
            items=items,
            notes="由 StrategyEngine 生成；执行前必须 preview + confirm + 绑定 rollback_snapshot",
        )

    # ---- 规则 → PlanItem 展开 ----
    def _expand_finding(self, plan_id: str, f: Finding) -> list[PlanItem]:
        if f.code == "word_price_bounds":
            return [
                self._word_item(plan_id, t, ActionType.ADJUST_PRICE)
                for t in f.targets if t.get("suggested")
            ]
        if f.code == "premium_backfire":
            return [
                self._crowd_premium_item(plan_id, t)
                for t in f.targets
            ]
        if f.code == "smart_targeting_leak":
            # 智能定向（crowdType=100）无法在接口关闭，只能压日预算或暂停计划。
            # 这里输出「暂停拉新计划」动作，预算细节由复盘 T+7 判定矩阵接管。
            return [
                self._campaign_pause_item(plan_id, t)
                for t in f.targets
            ]
        if f.code == "word_package_squeeze":
            return [
                self._word_package_item(plan_id, t, ratio=0.8)
                for t in f.targets
            ]
        if f.code in ("bare_traffic_share", "channel_threshold_mismatch"):
            # 这两条只能输出「提示」，不展开为可执行 item；UI 兜底通道
            return []
        return []

    def _word_item(self, plan_id: str, t: dict, action: ActionType) -> PlanItem:
        return PlanItem(
            item_id=self._iid(),
            plan_id=plan_id,
            target_type=TargetType.WORD,
            target_id=str(t.get("word_id") or t.get("word") or ""),
            target_name=str(t.get("word") or ""),
            scene=str(t.get("scene") or "onebpSearch"),
            campaign_id=str(t.get("campaign_id") or ""),
            adgroup_id=str(t.get("adgroup_id") or ""),
            action=action,
            before_value=str(t.get("bid_price") or ""),
            after_value=str(t.get("suggested") or ""),
            reason=str(t.get("reason") or f.title if False else ""),
            channel=ExecutionChannel.ONEBP_WRITE,
            status=ItemStatus.PENDING,
        )

    def _crowd_premium_item(self, plan_id: str, t: dict) -> PlanItem:
        return PlanItem(
            item_id=self._iid(),
            plan_id=plan_id,
            target_type=TargetType.CROWD,
            target_id=str(t.get("crowd_id") or ""),
            target_name=str(t.get("crowd_name") or ""),
            scene=str(t.get("scene") or "onebpSearch"),
            campaign_id=str(t.get("campaign_id") or ""),
            adgroup_id=str(t.get("adgroup_id") or ""),
            action=ActionType.ADJUST_PREMIUM,
            before_value=str(t.get("premium") or ""),
            after_value=str(t.get("suggested") or ""),
            reason=str(t.get("reason") or ""),
            channel=ExecutionChannel.ONEBP_WRITE,
            status=ItemStatus.PENDING,
        )

    def _campaign_pause_item(self, plan_id: str, t: dict) -> PlanItem:
        return PlanItem(
            item_id=self._iid(),
            plan_id=plan_id,
            target_type=TargetType.CAMPAIGN,
            target_id=str(t.get("campaign_id") or ""),
            target_name=str(t.get("campaign_name") or t.get("crowd_name") or ""),
            scene=str(t.get("scene") or "onebpSearch"),
            campaign_id=str(t.get("campaign_id") or ""),
            action=ActionType.PAUSE,
            before_value="start",
            after_value="pause",
            reason=str(t.get("reason") or "智能定向漏点，先暂停止血，T+7 复盘决定是否回加"),
            channel=ExecutionChannel.ONEBP_WRITE,
            status=ItemStatus.PENDING,
        )

    def _campaign_budget_item(self, plan_id: str, t: dict, ratio: float) -> PlanItem:
        return PlanItem(
            item_id=self._iid(),
            plan_id=plan_id,
            target_type=TargetType.BUDGET,
            target_id=str(t.get("campaign_id") or ""),
            target_name=str(t.get("campaign_name") or ""),
            scene=str(t.get("scene") or "onebpSearch"),
            campaign_id=str(t.get("campaign_id") or ""),
            action=ActionType.ADJUST_BUDGET,
            before_value=str(t.get("charge") or ""),
            after_value=str(round(float(t.get("charge") or 0) * ratio, 2)),
            reason=str(t.get("reason") or ""),
            channel=ExecutionChannel.ONEBP_WRITE,
            status=ItemStatus.PENDING,
        )

    def _word_package_item(self, plan_id: str, t: dict, ratio: float) -> PlanItem:
        return PlanItem(
            item_id=self._iid(),
            plan_id=plan_id,
            target_type=TargetType.BIDWORD_PACKAGE,
            target_id=str(t.get("package_id") or ""),
            target_name=str(t.get("package_name") or "流量智选"),
            scene="onebpSearch",
            campaign_id=str(t.get("campaign_id") or ""),
            action=ActionType.ADJUST_WORD_PACKAGE,
            before_value=str(t.get("charge") or ""),
            after_value=str(round(float(t.get("charge") or 0) * ratio, 2)),
            reason=str(t.get("reason") or "词包花费占比过高"),
            channel=ExecutionChannel.ONEBP_WRITE,
            status=ItemStatus.PENDING,
        )

    @staticmethod
    def _iid() -> str:
        return uuid.uuid4().hex[:12]
