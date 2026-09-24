"""Typed, evidence-driven plans for multi-step business analysis.

Skills describe reusable domain calculations.  This module sits one level
above them: it turns a question into a testable analysis objective, chooses
the minimum evidence needed to answer it, and states when the evidence is not
good enough to draw a conclusion.  Keeping this independent from the HTTP and
MCP layers makes new agent behaviours additive rather than another branch in
the request handler.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.modules.ai.schemas import (
    ArtifactSpec,
    CoverageSummary,
    Diagnosis,
    DiagnosisFinding,
    MCPEnvelope,
    RecommendedAction,
    SkillToolStep,
)


@dataclass(frozen=True)
class AnalysisIntent:
    """The semantic target that the executor must prove or disprove."""

    name: str
    goal: str
    comparison_dimension: str
    ranking_measure: str
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    hypotheses: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "goal": self.goal,
            "comparison_dimension": self.comparison_dimension,
            "ranking_measure": self.ranking_measure,
            "current_range": [self.current_start.isoformat(), self.current_end.isoformat()],
            "previous_range": [self.previous_start.isoformat(), self.previous_end.isoformat()],
            "hypotheses": list(self.hypotheses),
        }


@dataclass(frozen=True)
class AgentPlan:
    """A bounded execution plan with a concrete evidence-completion rule."""

    name: str
    primary_skill: str
    supporting_skills: tuple[str, ...]
    intent: AnalysisIntent
    calls: tuple[SkillToolStep, ...]
    completion_rule: str
    fallback_calls: tuple[SkillToolStep, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "primary_skill": self.primary_skill,
            "supporting_skills": list(self.supporting_skills),
            "intent": self.intent.as_dict(),
            "steps": [
                {"tool": step.tool, "purpose": step.description, "arguments": step.arguments}
                for step in self.calls
            ],
            "completion_rule": self.completion_rule,
        }

    def repair_calls(self, results: list[MCPEnvelope]) -> tuple[SkillToolStep, ...]:
        """Request raw daily evidence only when grouped comparison is unusable.

        A complete date coverage with zero grouped rows is not a collection
        failure.  The fallback verifies the raw source rows so the answer can
        distinguish an empty platform response from an incorrectly-shaped
        query instead of automatically asking the operator to recollect data.
        """
        traffic = _comparison_result(results, "traffic_sources")
        if self.name == "promotion-efficiency-diagnosis":
            return _promotion_drilldown_repairs(self, results)
        if traffic is None:
            return self.fallback_calls
        if traffic.status != "no_data" and _comparison_rows(traffic, "source"):
            return ()
        if traffic.coverage.missing_dates or traffic.coverage.partial_datasets:
            return ()
        return self.fallback_calls


def build_agent_plan(
    *,
    question: str,
    start_date: date | None,
    end_date: date | None,
    inherited_end_date: date | None = None,
    available_end_date: date | None = None,
) -> AgentPlan | None:
    """Build a plan for questions that require comparison, not a lookup.

    This registry only accepts questions with a clear comparison operation.
    Each accepted intent gets a separate evidence contract, so adding a new
    agent behaviour does not alter the execution of an existing Skill.
    """
    promotion_question = _is_promotion_efficiency_question(question)
    explicit_days = _comparison_days(question)
    days = explicit_days
    # Promotion questions are useful even when the operator did not phrase
    # them as a comparison.  Use the selected page range when it is explicit;
    # otherwise inspect a bounded seven-day window.  The comparison remains
    # adjacent and equal-length, so missing days cannot silently become zero.
    if days is None and promotion_question and start_date and end_date:
        days = (end_date - start_date).days + 1
    if days is None and promotion_question:
        days = 7
    if days is None:
        return None
    anchor = end_date or inherited_end_date or available_end_date
    if anchor is None:
        return None
    # If callers supplied a range, “最近 N 天” means the final N business
    # days inside that range, never a range relative to the machine clock.
    current_start = (
        start_date
        if promotion_question and explicit_days is None and start_date and end_date
        else anchor - timedelta(days=days - 1)
    )
    if current_start > anchor:
        return None
    if start_date and current_start < start_date:
        return None
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    window = (current_start, anchor, previous_start, previous_end)
    if _is_channel_growth_question(question):
        return _channel_growth_plan(days, window)
    if _is_recent_sales_growth_question(question):
        return _sales_growth_plan(days, window)
    if promotion_question:
        return _promotion_efficiency_plan(days, window)
    return None


def _channel_growth_plan(days: int, window: tuple[date, date, date, date]) -> AgentPlan:
    current_start, current_end, previous_start, previous_end = window
    intent = AnalysisIntent(
        name="channel-growth-comparison",
        goal=f"比较 {current_start.isoformat()} 至 {current_end.isoformat()} 与紧邻前 {days} 天，按一级流量来源的支付金额增量排序",
        comparison_dimension="一级流量来源",
        ranking_measure="支付金额绝对增量",
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=previous_end,
        hypotheses=(
            "增长来源需要按当前窗口减去等长前序窗口排序，不能按当前绝对值排序。",
            "推广归因成交可用于解释投放变化，但与一级流量来源可能重叠，不能相加为店铺销售。",
            "只有同口径窗口完整覆盖时，渠道变化才能列为已确认事实。",
        ),
    )
    base_arguments = {
        "start_date": current_start,
        "end_date": current_end,
        "limit": 100,
    }
    return AgentPlan(
        name="channel-growth-comparison",
        primary_skill="traffic-diagnosis",
        supporting_skills=("shop-overview-diagnosis", "promotion-roi", "data-quality-audit"),
        intent=intent,
        calls=(
            SkillToolStep(
                tool="data.coverage",
                arguments={
                    "datasets": ["store_overview", "traffic_sources", "promotion_campaigns"],
                    "start_date": previous_start,
                    "end_date": current_end,
                },
                description="先校验两段窗口的总盘、一级流量来源和推广计划日期覆盖",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={
                    **base_arguments,
                    "dataset": "store_overview",
                    "dimensions": [],
                    "measures": ["gmv", "visitors", "buyers"],
                },
                description="确认店铺支付金额、访客与买家的整体变化",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={
                    **base_arguments,
                    "dataset": "traffic_sources",
                    "dimensions": ["source"],
                    "measures": ["gmv", "visitors", "buyers"],
                    "order_by": ["-gmv"],
                },
                description="按一级流量来源比较两个等长窗口的支付金额增量",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={
                    **base_arguments,
                    "dataset": "promotion_campaigns",
                    "dimensions": ["scene"],
                    "measures": ["spend", "gmv", "buyers", "roi"],
                    "order_by": ["-gmv"],
                },
                description="复核推广场景的归因成交、花费与 ROI 变化，不与一级来源相加",
            ),
        ),
        fallback_calls=(
            SkillToolStep(
                tool="data.query",
                arguments={
                    "dataset": "traffic_sources",
                    "dimensions": ["date", "source"],
                    "measures": ["gmv", "visitors", "buyers"],
                    "start_date": previous_start,
                    "end_date": current_end,
                    "order_by": ["date", "-gmv"],
                    "limit": 100,
                },
                description="一级来源分组比较未返回行，回读逐日原始聚合以验证查询形状",
            ),
        ),
        completion_rule="总盘与一级流量来源均取得两个完整等长窗口，且每个来源都有当前、前序窗口的支付金额后才输出渠道排名。",
    )


def _sales_growth_plan(days: int, window: tuple[date, date, date, date]) -> AgentPlan:
    current_start, current_end, previous_start, _previous_end = window
    intent = AnalysisIntent(
        name="recent-sales-growth-diagnosis",
        goal=f"解释 {current_start.isoformat()} 至 {current_end.isoformat()} 相对紧邻前 {days} 天的销售变化，并分开确认结果、渠道和推广证据",
        comparison_dimension="总盘、一级流量来源、推广场景、商品",
        ranking_measure="支付金额绝对增量与支付转化率变化",
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=current_start - timedelta(days=1),
        hypotheses=(
            "先确认店铺支付金额是否真的增长，再拆支付买家、访客和支付转化率。",
            "一级流量来源和商品增量用于定位增长集中处；它们不是彼此可相加的总盘。",
            "推广归因成交和 ROI 仅用于解释投放相关变化，不当作已经证明的因果增量。",
        ),
    )

    compare_base = {"start_date": current_start, "end_date": current_end, "limit": 100}
    return AgentPlan(
        name="recent-sales-growth-diagnosis",
        primary_skill="shop-overview-diagnosis",
        supporting_skills=("traffic-diagnosis", "promotion-roi", "product-diagnosis", "data-quality-audit"),
        intent=intent,
        calls=(
            SkillToolStep(
                tool="data.coverage",
                arguments={
                    "datasets": ["store_overview", "traffic_sources", "promotion_campaigns", "products"],
                    "start_date": previous_start,
                    "end_date": current_end,
                },
                description="先校验两段窗口的总盘、来源、推广和商品数据覆盖",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={**compare_base, "dataset": "store_overview", "dimensions": [], "measures": ["gmv", "visitors", "buyers", "refund_amount"]},
                description="确认销售结果、访客、买家和退款的两窗口变化",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={**compare_base, "dataset": "traffic_sources", "dimensions": ["source"], "measures": ["gmv", "visitors", "buyers"], "order_by": ["-gmv"]},
                description="按一级流量来源定位支付金额增长集中处",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={**compare_base, "dataset": "promotion_campaigns", "dimensions": ["scene"], "measures": ["spend", "gmv", "buyers", "roi"], "order_by": ["-gmv"]},
                description="复核推广场景的归因成交、花费和 ROI 变化",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={**compare_base, "dataset": "products", "dimensions": ["product_id", "product_name"], "measures": ["gmv", "buyers", "visitors", "refund_amount"], "order_by": ["-gmv"]},
                description="按商品定位支付金额增量集中处",
            ),
        ),
        fallback_calls=(
            SkillToolStep(
                tool="data.query",
                arguments={
                    "dataset": "traffic_sources",
                    "dimensions": ["date", "source"],
                    "measures": ["gmv", "visitors", "buyers"],
                    "start_date": previous_start,
                    "end_date": current_end,
                    "order_by": ["date", "-gmv"],
                    "limit": 100,
                },
                description="来源分组比较未返回行，回读逐日原始聚合以验证查询形状",
            ),
        ),
        completion_rule="总盘必须完整比较；来源、推广和商品只在返回同口径两窗口记录时作为增长解释证据。",
    )


def _promotion_efficiency_plan(days: int, window: tuple[date, date, date, date]) -> AgentPlan:
    current_start, current_end, previous_start, previous_end = window
    intent = AnalysisIntent(
        name="promotion-efficiency-diagnosis",
        goal=(
            f"审计 {current_start.isoformat()} 至 {current_end.isoformat()} 的推广全量账户，"
            f"并与紧邻前 {days} 天比较，按场景→计划→单元→人群/关键词/商品定位低效与扩量候选"
        ),
        comparison_dimension="推广场景、计划、单元、人群、关键词、商品、内容",
        ranking_measure="花费覆盖下的归因成交、ROI、点击转化率和新客占比",
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=previous_end,
        hypotheses=(
            "先用推广计划全量聚合确认账户总盘，再按花费和效率筛选下钻对象。",
            "高点击低成交优先检查商品承接和流量匹配，不用继续加预算掩盖转化问题。",
            "高 ROI 计划只能进入小额阶梯测试；没有实验或对照时不称为因果增量或利润。",
            "缺失日期、缺失层级和平台确认无数据必须分开，不把缺失当作 0。",
        ),
    )
    current_args = {"start_date": current_start, "end_date": current_end}
    compare_args = {**current_args, "limit": 100}
    return AgentPlan(
        name="promotion-efficiency-diagnosis",
        primary_skill="promotion-roi",
        supporting_skills=("promotion-budget-planning", "product-diagnosis", "data-quality-audit"),
        intent=intent,
        calls=(
            SkillToolStep(
                tool="data.coverage",
                arguments={
                    "datasets": [
                        "store_overview", "promotion_campaigns", "promotion_adgroups",
                        "promotion_crowds", "promotion_keywords", "promotion_products", "promotion_contents",
                    ],
                    "start_date": previous_start,
                    "end_date": current_end,
                },
                description="先校验总盘和推广场景、计划、单元、人群、关键词、商品、内容的日期覆盖",
            ),
            SkillToolStep(
                tool="promotions.get_efficiency",
                arguments=current_args,
                description="读取全量推广账户和场景聚合，建立花费、归因成交、ROI、点击和新客总盘",
            ),
            SkillToolStep(
                tool="data.compare_periods",
                arguments={
                    **compare_args,
                    "dataset": "promotion_campaigns",
                    "dimensions": ["scene"],
                    "measures": ["spend", "gmv", "buyers", "clicks", "roi", "direct_roi", "click_conversion_rate", "new_buyer_share"],
                    "order_by": ["-spend"],
                },
                description="比较本期与前期推广场景的规模、归因效率和点击转化变化",
            ),
            SkillToolStep(
                tool="promotions.get_drilldown",
                arguments={**current_args, "level": "campaign", "order_by": "-spend", "page": 1, "page_size": 100},
                description="按计划层保留全量花费排序结果，供质量门选择低效和高效候选",
            ),
            SkillToolStep(
                tool="data.query",
                arguments={
                    **current_args,
                    "dataset": "promotion_contents",
                    "dimensions": ["scene", "campaign_id", "campaign_name", "content_id", "content_name", "content_type"],
                    "measures": ["impressions", "clicks", "spend", "gmv", "orders", "roi", "ctr", "cpc"],
                    "order_by": ["-spend"],
                    "limit": 200,
                },
                description="补充推广内容层证据，检查内容点击与成交承接",
            ),
        ),
        completion_rule=(
            "推广覆盖至少包含一个完整账户窗口；全量账户聚合和计划层结果必须返回，"
            "并对主要低效计划继续取得单元、人群、关键词或商品层证据后，才输出 P0/P1 动作。"
        ),
    )


def _promotion_drilldown_repairs(plan: AgentPlan, results: list[MCPEnvelope]) -> tuple[SkillToolStep, ...]:
    """Select the next bounded drilldown from observed spend and efficiency."""
    campaign_result = next(
        (item for item in results if item.tool == "promotions.get_drilldown" and item.data.get("level") == "campaign"),
        None,
    )
    efficiency = next((item for item in results if item.tool == "promotions.get_efficiency"), None)
    rows = list((campaign_result.data.get("rows") if campaign_result else None) or [])
    if not rows and efficiency is not None:
        rows = list(efficiency.data.get("campaigns") or [])
    if not rows:
        return ()

    def spend(row: dict[str, Any]) -> float:
        return _number(row.get("spend")) or 0.0

    def roi(row: dict[str, Any]) -> float:
        return _number(row.get("roi")) or 0.0

    low = [row for row in rows if spend(row) > 0 and (roi(row) < 1.5 or (_number(row.get("paid_amount")) or 0) == 0)]
    selected = sorted(low or rows, key=spend, reverse=True)[:2]
    existing_child_results = [
        item for item in results
        if item.tool == "promotions.get_drilldown" and item.data.get("level") in {"adgroup", "product", "audience", "keyword"}
    ]
    calls: list[SkillToolStep] = []
    if not existing_child_results:
        for row in selected:
            campaign_id = str(row.get("campaign_id") or row.get("dimension_id") or "").strip()
            if not campaign_id:
                continue
            for level, label in (("adgroup", "单元"), ("product", "商品")):
                calls.append(SkillToolStep(
                    tool="promotions.get_drilldown",
                    arguments={
                        "start_date": plan.intent.current_start,
                        "end_date": plan.intent.current_end,
                        "level": level,
                        "campaign_id": campaign_id,
                        "order_by": "-spend",
                        "page": 1,
                        "page_size": 100,
                    },
                    description=f"按低效/高影响计划 {campaign_id} 下钻{label}层，寻找可执行问题对象",
                ))
        return tuple(calls)

    # Audience and keyword rows are children of an adgroup rather than a
    # campaign.  Observe the first-stage adgroup results and only then select
    # the highest-impact units for the second evidence round.
    adgroup_rows = [
        row for item in existing_child_results if item.data.get("level") == "adgroup"
        for row in (item.data.get("rows") or [])
    ]
    low_adgroups = [row for row in adgroup_rows if spend(row) > 0 and (roi(row) < 1.5 or (_number(row.get("paid_amount")) or 0) == 0)]
    selected_adgroups = sorted(low_adgroups or adgroup_rows, key=spend, reverse=True)[:2]
    existing_leaf_keys = {
        (str(item.data.get("level")), str((item.context.filters or {}).get("adgroup_id") or ""))
        for item in existing_child_results if item.data.get("level") in {"audience", "keyword"}
    }
    for row in selected_adgroups:
        adgroup_id = str(row.get("dimension_id") or row.get("adgroup_id") or "").strip()
        if not adgroup_id:
            continue
        for level, label in (("audience", "人群"), ("keyword", "关键词")):
            if (level, adgroup_id) in existing_leaf_keys:
                continue
            calls.append(SkillToolStep(
                tool="promotions.get_drilldown",
                arguments={
                    "start_date": plan.intent.current_start,
                    "end_date": plan.intent.current_end,
                    "level": level,
                    "adgroup_id": adgroup_id,
                    "order_by": "-spend",
                    "page": 1,
                    "page_size": 100,
                },
                description=f"根据第一轮结果继续下钻单元 {adgroup_id} 的{label}层",
            ))
    return tuple(calls)


def diagnose_agent_plan(plan: AgentPlan, results: list[MCPEnvelope]) -> Diagnosis:
    """Synthesize an answer from exactly the evidence required by the plan."""
    if plan.name == "recent-sales-growth-diagnosis":
        return _sales_growth_diagnosis(plan, results)
    if plan.name == "promotion-efficiency-diagnosis":
        return _promotion_efficiency_diagnosis(plan, results)
    traffic = _comparison_result(results, "traffic_sources")
    overview = _comparison_result(results, "store_overview")
    promotions = _comparison_result(results, "promotion_campaigns")
    coverage = _merged_coverage(results, plan)
    plan_data = plan.as_dict()

    if traffic is None:
        detail = "一级流量来源比较工具没有返回，尚未得到渠道排名。"
        return _incomplete_diagnosis(plan, coverage, detail, "未执行到一级流量来源比较，不能输出哪个渠道增长最多。")

    rows = _channel_rows(traffic)
    if not rows:
        raw_verified = any(
            item.tool == "data.query" and item.data.get("dataset") == "traffic_sources"
            for item in results
        )
        if traffic.coverage.missing_dates or traffic.coverage.partial_datasets:
            detail = "一级流量来源的对比窗口不完整，缺失日期没有按 0 参与比较。"
            reason = "需要补齐实际缺失日期后，才能给出渠道增长排名。"
        elif raw_verified:
            detail = "两个窗口日期覆盖完整，但逐日一级来源查询也没有返回记录；这属于本轮可用数据为空，不会被误写成待补采。"
            reason = "请确认平台是否对该店铺/窗口返回一级来源报表，再决定是否需要采集。"
        else:
            detail = "一级流量来源没有可比较行，正在等待原始逐日查询验证。"
            reason = "没有来源行时不以 0/0 覆盖或周期汇总代替渠道排名。"
        return _incomplete_diagnosis(plan, coverage, detail, reason)

    lead = rows[0]
    total_delta = _comparison_metric(overview, "gmv", "delta")
    total_current = _comparison_metric(overview, "gmv", "current")
    total_previous = _comparison_metric(overview, "gmv", "previous")
    total_percent = _comparison_metric(overview, "gmv", "change_percent")
    source_delta = _comparison_metric(traffic, "gmv", "delta")
    source_current = _comparison_metric(traffic, "gmv", "current")
    source_previous = _comparison_metric(traffic, "gmv", "previous")
    conversion_current = _rate(_comparison_metric(traffic, "buyers", "current"), _comparison_metric(traffic, "visitors", "current"))
    conversion_previous = _rate(_comparison_metric(traffic, "buyers", "previous"), _comparison_metric(traffic, "visitors", "previous"))

    lead_detail = (
        f"{lead['来源']} 的支付金额由 {lead['前2天支付金额']:,.0f} 元增至 "
        f"{lead['最近2天支付金额']:,.0f} 元，增加 {lead['支付金额增量']:,.0f} 元"
        f"（{_percent_text(lead['支付金额增长率%'])}），为一级来源中绝对增量最大项。"
    )
    findings = [
        DiagnosisFinding(
            level="positive" if lead["支付金额增量"] > 0 else "warning",
            title=f"{lead['来源']} 是最近两天增长最多的一级来源",
            detail=lead_detail,
            metric_ids=["gmv", "visitors", "buyers"],
            evidence=["data.compare_periods:traffic_sources"],
            confidence="high" if traffic.status == "ok" else "medium",
        )
    ]
    if total_delta is not None:
        findings.append(DiagnosisFinding(
            level="info",
            title="总盘增长与渠道口径已分开核对",
            detail=(
                f"店铺支付金额由 {float(total_previous or 0):,.0f} 元增至 {float(total_current or 0):,.0f} 元，"
                f"增加 {float(total_delta):,.0f} 元（{_percent_text(total_percent)}）。"
                f"一级来源合计增加 {float(source_delta or 0):,.0f} 元；两者口径可能存在归因差异，不将来源合计当作财务总盘。"
            ),
            metric_ids=["gmv"],
            evidence=["data.compare_periods:store_overview", "data.compare_periods:traffic_sources"],
            confidence="high" if overview and overview.status == "ok" else "medium",
        ))
    if conversion_current is not None and conversion_previous is not None:
        findings.append(DiagnosisFinding(
            level="positive" if conversion_current >= conversion_previous else "warning",
            title="来源侧支付转化率已作为增长解释的反证检查",
            detail=(
                f"一级来源加权支付转化率从 {conversion_previous:.2f}% 变为 {conversion_current:.2f}%，"
                f"访客从 {float(_comparison_metric(traffic, 'visitors', 'previous') or 0):,.0f} 变为 "
                f"{float(_comparison_metric(traffic, 'visitors', 'current') or 0):,.0f}。"
                "这说明本轮增长不能只用流量规模解释，仍需结合各来源承接和商品结构验证。"
            ),
            metric_ids=["visitors", "buyers"],
            evidence=["data.compare_periods:traffic_sources"],
            confidence="high" if traffic.status == "ok" else "medium",
        ))

    promotion_rows = _comparison_rows(promotions, "scene")
    if promotion_rows:
        promotion_lead = max(
            (_promotion_row(current, previous) for current, previous in _join_rows(promotions, "scene")),
            key=lambda item: item["归因成交增量"],
        )
        findings.append(DiagnosisFinding(
            level="info",
            title=f"{promotion_lead['推广场景']} 是增长最大的推广归因场景",
            detail=(
                f"归因成交增加 {promotion_lead['归因成交增量']:,.0f} 元，花费变化 "
                f"{promotion_lead['花费增量']:,.0f} 元，ROI 从 "
                f"{_number_text(promotion_lead['前2天ROI'])} 变为 {_number_text(promotion_lead['最近2天ROI'])}。"
                "该结果用于解释投放变化，与一级流量来源可能重叠，不并入渠道增长排名。"
            ),
            metric_ids=["spend", "gmv", "roi"],
            evidence=["data.compare_periods:promotion_campaigns"],
            confidence="high" if promotions and promotions.status == "ok" else "medium",
        ))

    actions = [
        RecommendedAction(
            priority="P0",
            title=f"下钻 {lead['来源']} 的增长构成",
            detail=f"按 {lead['来源']} 的二级/三级来源、承接商品和活动触点继续比较前后两段窗口，先确认增长集中在何处，不把一级来源标签直接当作因果。",
            owner="流量运营",
            validation=f"拆出 {lead['来源']} 前三项支付金额增量来源，并核对其支付转化率与退款表现",
            observation_window="1-3天",
            expected_impact="明确可复用的来源、商品或承接组合，避免只按一级来源扩量。",
            confidence="high" if traffic.status == "ok" else "medium",
        ),
        RecommendedAction(
            priority="P1",
            title="复核增长窗口后的持续性",
            detail="连续观察后续 3-7 天同一一级来源的访客、支付买家、支付金额、退款和客单价；若只在活动窗口出现，不把它视为稳定趋势。",
            owner="经营运营",
            validation="后续窗口支付金额保持增长且退款率、支付转化率不明显恶化",
            observation_window="3-7天",
            expected_impact="区分短期活动脉冲与可持续的经营改善。",
        ),
    ]
    return Diagnosis(
        headline=findings[0].title,
        summary=lead_detail,
        findings=findings,
        actions=actions,
        artifacts=[
            ArtifactSpec(type="matrix", title="一级流量来源两窗口对比", rows=rows),
            ArtifactSpec(type="metric_table", title="分析计划与证据状态", rows=[
                {"分析目标": plan.intent.goal, "完成条件": plan.completion_rule, "证据状态": "已满足" if traffic.status == "ok" else traffic.status}
            ]),
        ],
        analysis_plan=plan_data,
        coverage=coverage,
        confidence="high" if traffic.status == "ok" and (overview is None or overview.status == "ok") else "medium",
        assumptions=[
            "渠道排名按一级流量来源的支付金额绝对增量计算，而不是按当前金额或增长率排序。",
            "一级流量来源与店铺总盘、推广归因成交不是同一可相加口径。",
        ],
        evidence_refs=["data.compare_periods:store_overview", "data.compare_periods:traffic_sources", "data.compare_periods:promotion_campaigns"],
        metric_definitions={
            "渠道支付金额增量": "最近2天一级来源支付金额 - 前2天同一一级来源支付金额",
            "来源侧支付转化率": "一级来源支付买家数 ÷ 一级来源访客数",
        },
        denominator_notes=["一级来源支付转化率以同一窗口内该来源访客数为分母。"],
        causal_boundary="本分析识别同口径渠道归因贡献的变化。没有实验、可信对照或平台增量报告时，不把来源增长表述为唯一因果或可相加的财务增量。",
        next_questions=[f"下钻 {lead['来源']} 的二级和三级来源", "比较增长来源承接的商品与退款", "查看增长窗口是否处于活动期"],
    )


def _promotion_efficiency_diagnosis(plan: AgentPlan, results: list[MCPEnvelope]) -> Diagnosis:
    efficiency = next((item for item in results if item.tool == "promotions.get_efficiency"), None)
    comparison = _comparison_result(results, "promotion_campaigns")
    campaign_drill = next(
        (item for item in results if item.tool == "promotions.get_drilldown" and item.data.get("level") == "campaign"),
        None,
    )
    coverage = _merged_coverage(results, plan)
    if efficiency is None or efficiency.status == "no_data":
        return _incomplete_diagnosis(
            plan,
            coverage,
            "推广账户总盘没有返回可用计划数据，暂时不能判断该降预算、止损还是扩量。",
            "先确认推广计划日报已采集且覆盖当前窗口，再重新执行推广诊断。",
        )

    summary = efficiency.data.get("summary") or {}
    spend = _number(summary.get("spend")) or 0.0
    paid_amount = _number(summary.get("paid_amount") or summary.get("gmv")) or 0.0
    roi = _number(summary.get("roi"))
    clicks = _number(summary.get("clicks")) or 0.0
    buyers = _number(summary.get("buyers")) or 0.0
    click_cvr = buyers / clicks * 100 if clicks else None
    campaigns = list((campaign_drill.data.get("rows") if campaign_drill else None) or efficiency.data.get("campaigns") or [])
    low_campaigns = [
        row for row in campaigns
        if (_number(row.get("spend")) or 0) > 0
        and ((_number(row.get("roi")) or 0) < 1.5 or (_number(row.get("paid_amount")) or 0) == 0)
    ]
    low_campaigns.sort(key=lambda row: _number(row.get("spend")) or 0, reverse=True)
    low_spend = sum(_number(row.get("spend")) or 0 for row in low_campaigns)
    low_share = low_spend / spend * 100 if spend else None
    no_gmv = [
        row for row in campaigns
        if (_number(row.get("spend")) or 0) > 0 and (_number(row.get("paid_amount")) or 0) == 0
    ]
    scale_candidates = [
        row for row in campaigns
        if (_number(row.get("spend")) or 0) > 0
        and (_number(row.get("roi")) or 0) >= 3
        and (_number(row.get("clicks")) or 0) > 0
    ]
    scale_candidates.sort(key=lambda row: _number(row.get("spend")) or 0, reverse=True)
    drill_levels = {
        item.data.get("level"): item for item in results
        if item.tool == "promotions.get_drilldown" and item.data.get("level")
    }
    layer_counts = {
        level: int((item.data.get("total") or 0))
        for level, item in drill_levels.items()
        if level != "campaign"
    }
    content_result = next((item for item in results if item.tool == "data.query" and item.data.get("dataset") == "promotion_contents"), None)
    content_rows = list((content_result.data.get("rows") if content_result else None) or [])
    findings: list[DiagnosisFinding] = [
        DiagnosisFinding(
            level="warning" if roi is not None and roi < 1 else "info",
            title="推广账户总盘已先于计划下钻确认",
            detail=(
                f"本期花费 {spend:,.0f} 元，平台归因成交 {paid_amount:,.0f} 元，整体 ROI "
                f"{_number_text(roi)}，点击 {clicks:,.0f}，成交买家 {buyers:,.0f}"
                f"，点击转化率 {_number_text(click_cvr)}%。"
                " ROI/归因成交是投放效率口径，不等于利润或已经证明的增量。"
            ),
            metric_ids=["promotion_spend", "promotion_roi", "click_conversion_rate"],
            evidence=["promotions.get_efficiency"],
            confidence="high" if efficiency.status == "ok" and not coverage.missing_dates else "medium",
        )
    ]
    if low_campaigns:
        top = low_campaigns[:3]
        names = "、".join(str(row.get("dimension_name") or row.get("campaign_name") or row.get("dimension_id") or "未命名计划") for row in top)
        findings.append(DiagnosisFinding(
            level="critical" if low_share is not None and low_share >= 30 else "warning",
            title="高花费低效率计划需要先止损复核",
            detail=(
                f"识别 {len(low_campaigns)} 个 ROI<1.5 或无归因成交的计划，预计花费 {low_spend:,.0f} 元"
                f"（账户花费占比 {_number_text(low_share)}%）。优先对象：{names}。"
                " 该判断只说明归因成交未覆盖/接近覆盖花费，不直接等于亏损。"
            ),
            metric_ids=["promotion_spend", "promotion_roi"],
            evidence=["promotions.get_drilldown:campaign", *[f"promotions.get_drilldown:{level}" for level in layer_counts]],
            confidence="high" if campaign_drill and campaign_drill.status == "ok" else "medium",
        ))
    if no_gmv:
        findings.append(DiagnosisFinding(
            level="warning",
            title="存在点击或花费但无归因成交的计划",
            detail=f"共有 {len(no_gmv)} 个计划有花费但归因成交为 0；先检查关键词/人群匹配、落地商品、价格与库存承接。",
            metric_ids=["clicks", "gmv", "click_conversion_rate"],
            evidence=["promotions.get_drilldown:campaign"],
            confidence="medium",
        ))
    if scale_candidates:
        candidate = scale_candidates[0]
        candidate_name = str(candidate.get("dimension_name") or candidate.get("campaign_name") or candidate.get("dimension_id") or "未命名计划")
        findings.append(DiagnosisFinding(
            level="positive",
            title="存在可进入小额阶梯测试的高效率候选",
            detail=(
                f"{candidate_name} 当前花费 {_number(candidate.get('spend')) or 0:,.0f} 元，ROI {_number_text(_number(candidate.get('roi')))}，"
                "只能作为扩量假设；应先做 10%~20% 预算阶梯，观察边际 ROI、点击转化率和新客质量。"
            ),
            metric_ids=["promotion_roi", "promotion_spend"],
            evidence=["promotions.get_drilldown:campaign"],
            confidence="medium",
        ))
    if comparison is not None and comparison.data.get("comparable"):
        findings.append(DiagnosisFinding(
            level="info",
            title="推广场景趋势已作为反证检查",
            detail="场景层本期与前期覆盖完整，可继续区分是花费扩张、点击承接还是成交效率变化；场景归因与店铺总盘不相加。",
            metric_ids=["promotion_spend", "promotion_roi"],
            evidence=["data.compare_periods:promotion_campaigns"],
            confidence="high",
        ))
    elif comparison is not None:
        findings.append(DiagnosisFinding(
            level="info",
            title="推广场景趋势不可严格比较",
            detail="本期或前期存在缺失日期/数据集不完整，趋势只保留当前窗口描述，不把缺失日期当作 0。",
            metric_ids=["promotion_spend", "promotion_roi"],
            evidence=["data.compare_periods:promotion_campaigns"],
            confidence="low",
        ))

    actions: list[RecommendedAction] = []
    if low_campaigns:
        first = low_campaigns[0]
        first_id = str(first.get("campaign_id") or first.get("dimension_id") or "")
        first_name = str(first.get("dimension_name") or first.get("campaign_name") or first_id or "低效计划")
        actions.append(RecommendedAction(
            priority="P0",
            title=f"先复核并限额 {first_name}",
            detail="沿计划→单元→关键词/人群→商品检查花费集中对象；在未确认承接和归因窗口前，暂停自动加预算，必要时先降低预算或暂停无成交对象。",
            owner="推广运营",
            validation="未来 1-3 天该计划的花费、点击转化率、直接/间接成交和退款表现改善，且低效花费占比下降",
            observation_window="1-3天",
            expected_impact="降低无效花费暴露，保留可复盘的变更前基线。",
            object_type="campaign",
            object_id=first_id,
            problem="高花费低归因效率",
            verify_metric="ROI、点击转化率、无成交花费占比",
            stop_condition="花费继续增长但点击转化率和归因成交无改善",
            confidence="high" if campaign_drill else "medium",
        ))
    if no_gmv:
        actions.append(RecommendedAction(
            priority="P1",
            title="处理点击有量但无成交的承接断点",
            detail="优先检查人群/关键词与商品的相关性、详情首屏、活动价、库存和落地页；不要只通过提高出价放大该断点。",
            owner="商品运营",
            validation="点击转化率、加购率和商品库存承接在连续 3 天内改善",
            observation_window="3-7天",
            expected_impact="把问题从投放流量规模转化为可验证的商品承接改善。",
            verify_metric="点击转化率、加购率、支付买家",
            stop_condition="点击增加而加购/支付继续不变或退款上升",
        ))
    if scale_candidates:
        candidate = scale_candidates[0]
        actions.append(RecommendedAction(
            priority="P2",
            title="对高效率计划做小额阶梯测试",
            detail="仅在同口径窗口完整时，将预算提高 10%~20%，设置边际 ROI 和点击转化率止损线；测试通过再继续扩量。",
            owner="推广运营",
            validation="测试组相对基线的边际 ROI 不明显下降，新增花费和归因成交同步可解释",
            observation_window="3-7天",
            expected_impact="验证可扩量性，而不是把历史 ROI 直接外推为利润。",
            object_type="campaign",
            object_id=str(candidate.get("campaign_id") or candidate.get("dimension_id") or ""),
            problem="高效率但扩量假设未验证",
            verify_metric="边际 ROI、点击转化率、新客占比",
            stop_condition="边际 ROI 低于基线或点击转化率明显恶化",
            confidence="medium",
        ))
    if not actions:
        actions.append(RecommendedAction(
            priority="P1",
            title="保持当前预算并补齐层级证据",
            detail="当前没有足够的高影响低效对象或扩量候选；先补齐计划下的单元、人群、关键词和商品层数据，再做动作。",
            owner="数据运营",
            validation="推广覆盖完整，且至少有一个计划层及其下钻层返回可比较结果",
            observation_window="完成后立即复跑",
            expected_impact="避免在样本不足时直接改预算。",
            confidence="low",
        ))

    artifact_rows = [{
        "指标": "账户花费", "当前值": round(spend, 2), "归因成交": round(paid_amount, 2), "ROI": roi,
        "点击": round(clicks, 2), "成交买家": round(buyers, 2), "点击转化率%": click_cvr,
        "覆盖状态": "完整" if not coverage.missing_dates and not coverage.partial_datasets else "部分覆盖",
    }]
    campaign_rows = []
    for row in campaigns[:30]:
        campaign_rows.append({
            "计划": row.get("dimension_name") or row.get("campaign_name") or row.get("dimension_id") or "未命名计划",
            "计划ID": row.get("campaign_id") or row.get("dimension_id") or "",
            "花费": _number(row.get("spend")),
            "归因成交": _number(row.get("paid_amount")),
            "ROI": _number(row.get("roi")),
            "点击": _number(row.get("clicks")),
            "成交买家": _number(row.get("buyers")),
            "问题标签": "高花费低效率" if row in low_campaigns else "",
        })
    if content_rows:
        content_rows = content_rows[:30]
    artifacts = [
        ArtifactSpec(type="metric_table", title="推广账户总盘", rows=artifact_rows),
        ArtifactSpec(type="matrix", title="推广计划全量效率", rows=campaign_rows),
        ArtifactSpec(type="metric_table", title="推广层级证据状态", rows=[
            {"层级": level, "返回行数": count, "用途": "定位可执行对象"} for level, count in sorted(layer_counts.items())
        ] or [{"层级": "计划", "返回行数": len(campaigns), "用途": "计划层总盘"}]),
    ]
    if content_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="推广内容承接", rows=content_rows))
    return Diagnosis(
        headline=("推广账户存在高花费低效率暴露" if low_campaigns else "推广账户总盘与层级证据已完成"),
        summary=(
            f"{plan.intent.current_start.isoformat()} 至 {plan.intent.current_end.isoformat()}：花费 {spend:,.0f} 元，"
            f"平台归因成交 {paid_amount:,.0f} 元，ROI {_number_text(roi)}。"
            "结论按全量账户分母计算，Top 计划只用于定位，不代替总计。"
        ),
        findings=findings,
        actions=actions,
        artifacts=artifacts,
        analysis_plan=plan.as_dict(),
        coverage=coverage,
        confidence="high" if efficiency.status == "ok" and not coverage.missing_dates else "medium" if efficiency.status == "ok" else "low",
        assumptions=[
            "ROI = 平台归因成交 ÷ 推广花费；不等于利润率。",
            "推广场景、计划、单元、人群、关键词、商品和内容存在层级包含关系，不把各层金额相加。",
            "Top N 仅用于展示和下钻选择，账户总盘使用全量计划聚合。",
        ],
        missing_inputs=["完整商品成本、平台费、优惠补贴和履约成本"],
        evidence_refs=[item.tool + (f":{item.data.get('dataset')}" if item.data.get("dataset") else "") for item in results],
        metric_definitions={
            "整体 ROI": "推广计划全量平台归因成交金额 ÷ 推广花费",
            "点击转化率": "成交买家数 ÷ 点击量",
            "新客占比": "成交新客数 ÷ 成交买家数（有字段时）",
        },
        denominator_notes=["账户 ROI、低效花费占比和计划排序都使用全量推广计划作为分母。", "缺失日期不按 0 参与趋势和效率判断。"],
        causal_boundary="本分析只识别平台归因贡献与投放效率，不能在没有实验、可信对照或平台增量报告时声称广告带来了因果增量，也不能用 ROI 推导利润。",
        next_questions=["下钻低效计划的关键词和人群", "检查高点击低成交商品的详情和库存承接", "对高效率计划做 10%~20% 预算阶梯测试并复盘 T+7"],
    )

def _sales_growth_diagnosis(plan: AgentPlan, results: list[MCPEnvelope]) -> Diagnosis:
    """Explain a recent sales change without mixing it with a long period."""
    overview = _comparison_result(results, "store_overview")
    traffic = _comparison_result(results, "traffic_sources")
    promotions = _comparison_result(results, "promotion_campaigns")
    products = _comparison_result(results, "products")
    coverage = _merged_coverage(results, plan)
    if overview is None or overview.status == "no_data":
        return _incomplete_diagnosis(
            plan,
            coverage,
            "总盘没有返回两个等长窗口的支付金额，无法先确认销售是否增长。",
            "先恢复店铺日概览的两窗口数据，再判断增长原因。",
        )

    current_gmv = _comparison_metric(overview, "gmv", "current") or 0.0
    previous_gmv = _comparison_metric(overview, "gmv", "previous") or 0.0
    gmv_delta = _comparison_metric(overview, "gmv", "delta") or 0.0
    gmv_change = _comparison_metric(overview, "gmv", "change_percent")
    current_visitors = _comparison_metric(overview, "visitors", "current")
    previous_visitors = _comparison_metric(overview, "visitors", "previous")
    current_buyers = _comparison_metric(overview, "buyers", "current")
    previous_buyers = _comparison_metric(overview, "buyers", "previous")
    current_conversion = _rate(current_buyers, current_visitors)
    previous_conversion = _rate(previous_buyers, previous_visitors)
    headline = (
        f"最近{(plan.intent.current_end - plan.intent.current_start).days + 1}天支付金额增长 {gmv_delta:,.0f} 元"
        if gmv_delta > 0 else f"最近{(plan.intent.current_end - plan.intent.current_start).days + 1}天支付金额没有增长"
    )
    summary = (
        f"支付金额由 {previous_gmv:,.0f} 元变为 {current_gmv:,.0f} 元，变化 {gmv_delta:+,.0f} 元"
        f"（{_percent_text(gmv_change)}）。以下证据只比较 {plan.intent.previous_start.isoformat()} 至 "
        f"{plan.intent.previous_end.isoformat()} 与 {plan.intent.current_start.isoformat()} 至 {plan.intent.current_end.isoformat()}。"
    )
    findings = [DiagnosisFinding(
        level="positive" if gmv_delta > 0 else "warning",
        title="销售变化已由总盘两窗口确认",
        detail=summary,
        metric_ids=["gmv", "visitors", "buyers"],
        evidence=["data.compare_periods:store_overview"],
        confidence="high" if overview.status == "ok" else "medium",
    )]
    if current_conversion is not None and previous_conversion is not None:
        conversion_direction = "改善" if current_conversion > previous_conversion else "下降" if current_conversion < previous_conversion else "持平"
        findings.append(DiagnosisFinding(
            level="positive" if current_conversion > previous_conversion else "warning" if current_conversion < previous_conversion else "info",
            title=f"支付转化率{conversion_direction}是已确认的结果解释",
            detail=(
                f"支付买家从 {float(previous_buyers or 0):,.0f} 变为 {float(current_buyers or 0):,.0f}，"
                f"访客从 {float(previous_visitors or 0):,.0f} 变为 {float(current_visitors or 0):,.0f}，"
                f"支付转化率从 {previous_conversion:.2f}% 变为 {current_conversion:.2f}%。"
                "这是经营结果的同口径拆解，不直接等同于某个活动或投放动作的因果效果。"
            ),
            metric_ids=["buyers", "visitors"],
            evidence=["data.compare_periods:store_overview"],
            confidence="high" if overview.status == "ok" else "medium",
        ))

    channel_rows = _channel_rows(traffic) if traffic is not None else []
    channel_lead = next((item for item in channel_rows if item["支付金额增量"] > 0), None)
    if channel_lead:
        findings.append(DiagnosisFinding(
            level="info",
            title=f"增长集中在一级来源：{channel_lead['来源']}",
            detail=(
                f"该来源支付金额增加 {channel_lead['支付金额增量']:,.0f} 元，"
                f"由 {channel_lead['前2天支付金额']:,.0f} 元变为 {channel_lead['最近2天支付金额']:,.0f} 元。"
                "它标出增长集中处，仍需下钻来源层级和承接商品才能确认具体驱动。"
            ),
            metric_ids=["gmv"],
            evidence=["data.compare_periods:traffic_sources"],
            confidence="high" if traffic and traffic.status == "ok" else "medium",
        ))

    promotion_rows = _comparison_rows(promotions, "scene")
    promotion_lead = None
    if promotion_rows:
        candidates = [_promotion_row(current, previous) for current, previous in _join_rows(promotions, "scene")]
        promotion_lead = max(candidates, key=lambda item: item["归因成交增量"], default=None)

    product_rows = _product_growth_rows(products)
    artifacts = [
        ArtifactSpec(type="metric_table", title="销售增长两窗口总盘", rows=[{
            "前2天支付金额": round(previous_gmv, 2),
            "最近2天支付金额": round(current_gmv, 2),
            "支付金额增量": round(gmv_delta, 2),
            "支付金额增长率%": gmv_change,
            "前2天支付转化率%": previous_conversion,
            "最近2天支付转化率%": current_conversion,
        }]),
        ArtifactSpec(type="matrix", title="一级流量来源两窗口对比", rows=channel_rows),
        ArtifactSpec(type="metric_table", title="分析计划与证据状态", rows=[{
            "分析目标": plan.intent.goal,
            "完成条件": plan.completion_rule,
            "证据状态": "已满足" if overview.status == "ok" else overview.status,
        }]),
    ]
    if product_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="支付金额增长商品", rows=product_rows[:20]))

    actions = [
        RecommendedAction(
            priority="P0",
            title=f"下钻 {channel_lead['来源']} 的增长来源" if channel_lead else "下钻一级来源增长构成",
            detail=(
                f"按 {channel_lead['来源']} 的二级/三级来源、承接商品和活动触点继续比较两个窗口，"
                "先验证增长是否由具体来源和商品组合贡献。"
                if channel_lead else "一级来源数据未能定位正向增量时，先核对来源覆盖和各来源的支付金额变化。"
            ),
            owner="流量运营",
            validation="输出来源层级、商品、支付转化率和退款的同口径增量表",
            observation_window="1-3天",
            expected_impact="将总盘增长拆成可验证的来源和商品组合。",
        ),
        RecommendedAction(
            priority="P1",
            title="复核增长商品的退款与承接质量",
            detail="针对支付金额增量最高的商品检查活动价、库存、详情承接和退款；支付金额增长不应以退款率或支付转化率恶化为代价。",
            owner="商品运营",
            validation="增长商品的支付转化率稳定，退款率不明显高于前序窗口",
            observation_window="3-7天",
            expected_impact="区分可持续成交改善与短期促销脉冲。",
        ),
    ]
    if promotion_lead and promotion_lead["归因成交增量"] > 0:
        findings.append(DiagnosisFinding(
            level="info",
            title=f"{promotion_lead['推广场景']} 的推广归因成交同步增长",
            detail=(
                f"归因成交增加 {promotion_lead['归因成交增量']:,.0f} 元，花费变化 {promotion_lead['花费增量']:,.0f} 元，"
                f"ROI 从 {_number_text(promotion_lead['前2天ROI'])} 变为 {_number_text(promotion_lead['最近2天ROI'])}。"
                "这是平台归因的相关证据，不能与一级来源或店铺销售相加，也不单独证明因果。"
            ),
            metric_ids=["spend", "gmv", "roi"],
            evidence=["data.compare_periods:promotion_campaigns"],
            confidence="high" if promotions and promotions.status == "ok" else "medium",
        ))
    return Diagnosis(
        headline=headline,
        summary=summary,
        findings=findings,
        actions=actions,
        artifacts=artifacts,
        analysis_plan=plan.as_dict(),
        coverage=coverage,
        confidence="high" if overview.status == "ok" and traffic and traffic.status == "ok" else "medium",
        assumptions=[
            "支付金额、访客与支付买家均按两个等长窗口比较；没有把整周或上月结果混入本轮结论。",
            "商品、来源和推广为不同归因/统计口径，不作为可相加的销售拆分。",
        ],
        evidence_refs=["data.compare_periods:store_overview", "data.compare_periods:traffic_sources", "data.compare_periods:promotion_campaigns", "data.compare_periods:products"],
        metric_definitions={
            "支付转化率": "支付买家数 ÷ 访客数",
            "支付金额增量": "最近2天支付金额 - 前2天支付金额",
        },
        denominator_notes=["支付转化率的分母为同一窗口店铺访客数。"],
        causal_boundary="本轮只建立销售变化与来源、推广、商品的同口径描述性关联。没有实验、可信对照或平台增量报告时，不把活动、推广或商品变化表述为唯一因果。",
        next_questions=["下钻增长最大的一级来源", "查看增长商品的退款与活动价", "验证增长窗口后 3-7 天的持续性"],
    )


def _incomplete_diagnosis(plan: AgentPlan, coverage: CoverageSummary, detail: str, reason: str) -> Diagnosis:
    if plan.name == "recent-sales-growth-diagnosis":
        subject = "销售增长诊断"
    elif plan.name == "promotion-efficiency-diagnosis":
        subject = "推广效率诊断"
    else:
        subject = "一级流量来源"
    return Diagnosis(
        headline=f"{subject}尚不能形成可靠结论",
        summary=detail,
        findings=[DiagnosisFinding(level="warning", title="分析计划证据未完成", detail=detail, confidence="low")],
        actions=[RecommendedAction(
            priority="P0",
            title="完成分析计划所需证据",
            detail=reason,
            owner="数据运营",
            validation=plan.completion_rule,
            observation_window="完成后立即复跑",
            confidence="low",
        )],
        artifacts=[ArtifactSpec(type="metric_table", title="分析计划与证据状态", rows=[{
            "分析目标": plan.intent.goal,
            "完成条件": plan.completion_rule,
            "证据状态": "未满足",
        }])],
        analysis_plan=plan.as_dict(),
        coverage=coverage,
        confidence="low",
        assumptions=["缺失日期不按 0 参与渠道增长计算。"],
        causal_boundary=(
            "未取得可比较的推广证据时，不输出投放效率或预算动作结论。"
            if plan.name == "promotion-efficiency-diagnosis"
            else "未取得可比较的一级来源记录时，不输出渠道增长归因结论。"
        ),
    )


def _is_promotion_efficiency_question(question: str) -> bool:
    lowered = question.casefold()
    if _is_budget_planning_question(question):
        # Keep the existing budget-planning skill's target/constraint
        # contract.  Efficiency diagnosis can still recommend a test, but it
        # must not replace an explicit budget-allocation request.
        return False
    promotion_terms = ("推广", "投放", "广告", "roi", "投产", "花费", "计划", "人群", "关键词", "预算")
    intent_terms = ("分析", "诊断", "效率", "低效", "高花费", "投产", "应该", "哪些", "怎么", "如何", "为什么", "复盘", "优化", "表现", "扩量", "降预算")
    if not any(token in lowered for token in promotion_terms) or not any(token in lowered for token in intent_terms):
        return False
    # A store-wide question may mention promotion as one of many domains. It
    # belongs to the overview orchestrator unless promotion is the explicit
    # subject of the request.
    broad = any(token in lowered for token in ("店铺", "全店", "整体", "经营", "总盘"))
    other_domains = sum(token in lowered for token in ("流量", "商品", "客服", "库存", "评价", "客户", "直播"))
    explicit_focus = any(token in lowered for token in ("推广效率", "投放效率", "计划效率", "低效计划", "推广roi", "推广 roi", "投放roi", "投放 roi"))
    return not (broad and other_domains >= 2 and not explicit_focus)


def _is_budget_planning_question(question: str) -> bool:
    lowered = question.casefold().strip()
    return any(token in lowered for token in ("预算怎么分", "预算怎么拆", "预算分配", "预算规划", "预算节奏", "目标roi", "目标投产", "总预算", "值得加预算", "值得投", "加预算"))


def _is_channel_growth_question(question: str) -> bool:
    lowered = question.casefold()
    channel_terms = ("渠道", "来源", "流量来源")
    comparison_terms = ("比较", "对比", "增长", "增加", "增长较多", "哪个")
    period_terms = ("最近", "近", "前", "上一", "上")
    return all(any(token in lowered for token in terms) for terms in (channel_terms, comparison_terms, period_terms))


def _is_recent_sales_growth_question(question: str) -> bool:
    lowered = question.casefold()
    sales_terms = ("销售", "成交", "支付金额", "gmv")
    growth_terms = ("增长", "上升", "增加", "变好")
    reason_terms = ("为什么", "原因", "怎么", "分析", "诊断")
    return (
        any(term in lowered for term in sales_terms)
        and any(term in lowered for term in growth_terms)
        and any(term in lowered for term in reason_terms)
    )


def _comparison_days(question: str) -> int | None:
    match = re.search(r"(?:最近|近)\s*(\d+)\s*天", question)
    if match:
        days = int(match.group(1))
        return days if 1 < days <= 31 else None
    if "最近两天" in question or "近两天" in question:
        return 2
    return None


def _comparison_result(results: list[MCPEnvelope], dataset: str) -> MCPEnvelope | None:
    return next((item for item in results if item.tool == "data.compare_periods" and item.data.get("dataset") == dataset), None)


def _comparison_metric(result: MCPEnvelope | None, metric: str, key: str) -> float | None:
    if result is None:
        return None
    value = ((result.data.get("comparisons") or {}).get(metric) or {}).get(key)
    return float(value) if value is not None else None


def _comparison_rows(result: MCPEnvelope | None, dimension: str) -> list[dict[str, Any]]:
    if result is None:
        return []
    return [dict(item) for item in ((result.data.get("current") or {}).get("rows") or []) if item.get(dimension) not in (None, "")]


def _join_rows(result: MCPEnvelope | None, dimension: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if result is None:
        return []
    current = {str(item.get(dimension)): dict(item) for item in ((result.data.get("current") or {}).get("rows") or []) if item.get(dimension) not in (None, "")}
    previous = {str(item.get(dimension)): dict(item) for item in ((result.data.get("previous") or {}).get("rows") or []) if item.get(dimension) not in (None, "")}
    return [(current.get(key, {}), previous.get(key, {})) for key in set(current) | set(previous)]


def _channel_rows(result: MCPEnvelope) -> list[dict[str, Any]]:
    rows = []
    for current, previous in _join_rows(result, "source"):
        current_gmv = _number(current.get("gmv")) or 0.0
        previous_gmv = _number(previous.get("gmv")) or 0.0
        current_visitors = _number(current.get("visitors")) or 0.0
        previous_visitors = _number(previous.get("visitors")) or 0.0
        current_buyers = _number(current.get("buyers")) or 0.0
        previous_buyers = _number(previous.get("buyers")) or 0.0
        rows.append({
            "来源": current.get("source") or previous.get("source") or "未命名来源",
            "前2天支付金额": round(previous_gmv, 2),
            "最近2天支付金额": round(current_gmv, 2),
            "支付金额增量": round(current_gmv - previous_gmv, 2),
            "支付金额增长率%": _change_percent(current_gmv, previous_gmv),
            "前2天访客": round(previous_visitors, 2),
            "最近2天访客": round(current_visitors, 2),
            "前2天支付买家": round(previous_buyers, 2),
            "最近2天支付买家": round(current_buyers, 2),
            "前2天支付转化率%": _rate(previous_buyers, previous_visitors),
            "最近2天支付转化率%": _rate(current_buyers, current_visitors),
        })
    return sorted(rows, key=lambda item: float(item["支付金额增量"]), reverse=True)


def _product_growth_rows(result: MCPEnvelope | None) -> list[dict[str, Any]]:
    rows = []
    for current, previous in _join_rows(result, "product_id"):
        current_gmv = _number(current.get("gmv")) or 0.0
        previous_gmv = _number(previous.get("gmv")) or 0.0
        rows.append({
            "商品ID": current.get("product_id") or previous.get("product_id") or "--",
            "商品": current.get("product_name") or previous.get("product_name") or "未命名商品",
            "前2天支付金额": round(previous_gmv, 2),
            "最近2天支付金额": round(current_gmv, 2),
            "支付金额增量": round(current_gmv - previous_gmv, 2),
            "支付金额增长率%": _change_percent(current_gmv, previous_gmv),
            "前2天退款金额": round(_number(previous.get("refund_amount")) or 0.0, 2),
            "最近2天退款金额": round(_number(current.get("refund_amount")) or 0.0, 2),
        })
    return sorted(rows, key=lambda item: float(item["支付金额增量"]), reverse=True)


def _promotion_row(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    current_spend = _number(current.get("spend")) or 0.0
    previous_spend = _number(previous.get("spend")) or 0.0
    current_gmv = _number(current.get("gmv")) or 0.0
    previous_gmv = _number(previous.get("gmv")) or 0.0
    return {
        "推广场景": current.get("scene") or previous.get("scene") or "未命名场景",
        "归因成交增量": round(current_gmv - previous_gmv, 2),
        "花费增量": round(current_spend - previous_spend, 2),
        "最近2天ROI": _number(current.get("roi")),
        "前2天ROI": _number(previous.get("roi")),
    }


def _merged_coverage(results: list[MCPEnvelope], plan: AgentPlan) -> CoverageSummary:
    if plan.name == "recent-sales-growth-diagnosis":
        preferred = _comparison_result(results, "store_overview")
    elif plan.name == "promotion-efficiency-diagnosis":
        audit = next((item for item in results if item.tool == "data.coverage"), None)
        efficiency = next((item for item in results if item.tool == "promotions.get_efficiency"), None)
        comparison = _comparison_result(results, "promotion_campaigns")
        candidates = [item for item in (audit, efficiency, comparison) if item is not None]
        if candidates:
            expected_days = (plan.intent.current_end - plan.intent.current_start).days + 1
            missing_dates = sorted({day for item in candidates for day in item.coverage.missing_dates})
            preferred_coverage = CoverageSummary(
                expected_days=expected_days,
                covered_days=min((item.coverage.covered_days for item in candidates), default=0),
                missing_dates=missing_dates,
                missing_datasets=list(dict.fromkeys(name for item in candidates for name in item.coverage.missing_datasets)),
                partial_datasets=list(dict.fromkeys(name for item in candidates for name in item.coverage.partial_datasets)),
                failed_datasets=list(dict.fromkeys(name for item in candidates for name in item.coverage.failed_datasets)),
                no_data_datasets=list(dict.fromkeys(name for item in candidates for name in item.coverage.no_data_datasets)),
                no_data_dates=list(dict.fromkeys(day for item in candidates for day in item.coverage.no_data_dates)),
                latest_data_date=max((item.coverage.latest_data_date for item in candidates if item.coverage.latest_data_date), default=None),
            )
            return preferred_coverage
        preferred = None
    else:
        preferred = _comparison_result(results, "traffic_sources")
    if preferred is not None:
        return preferred.coverage
    return CoverageSummary(
        expected_days=(plan.intent.current_end - plan.intent.current_start).days + 1,
        covered_days=0,
        missing_dates=[plan.intent.current_start.isoformat(), plan.intent.current_end.isoformat()],
    )


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _rate(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100, 2)


def _change_percent(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def _percent_text(value: float | None) -> str:
    return "--" if value is None else f"{value:+.1f}%"


def _number_text(value: float | None) -> str:
    return "--" if value is None else f"{value:.2f}"
