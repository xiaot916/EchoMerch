from datetime import date

from app.modules.ai.agent_planner import (
    _promotion_drilldown_repairs,
    build_agent_plan,
    diagnose_agent_plan,
)
from app.modules.ai.schemas import (
    AIConversationState,
    AnalysisContext,
    AnalysisRequest,
    CoverageSummary,
    MCPEnvelope,
)
from app.modules.ai.service import AIAnalysisService


def test_channel_growth_question_builds_a_comparison_plan() -> None:
    plan = build_agent_plan(
        question="最近两天和前两天比较哪个渠道增长较多？",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert plan is not None
    assert plan.primary_skill == "traffic-diagnosis"
    assert plan.intent.current_start == date(2026, 9, 6)
    assert plan.intent.previous_start == date(2026, 9, 4)
    tools = [step.tool for step in plan.calls]
    assert tools == ["data.coverage", "data.compare_periods", "data.compare_periods", "data.compare_periods"]
    traffic_call = next(step for step in plan.calls if step.arguments.get("dataset") == "traffic_sources")
    assert traffic_call.arguments["dimensions"] == ["source"]
    assert traffic_call.arguments["start_date"] == date(2026, 9, 6)


def test_channel_growth_analysis_uses_complete_daily_evidence_not_generic_exploration() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="最近两天和前两天比较哪个渠道增长较多？",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
            page_context={"page_key": "ai"},
            use_model=False,
        ),
        store_id=1,
    )

    assert result.skill.name == "traffic-diagnosis"
    assert result.diagnosis.analysis_plan["name"] == "channel-growth-comparison"
    assert result.diagnosis.coverage.covered_days == 2
    assert result.diagnosis.coverage.expected_days == 2
    assert not result.diagnosis.coverage.missing_dates
    tools = [item.tool for item in result.mcp_results]
    assert "data.catalog" not in tools
    assert any(item.tool == "data.compare_periods" and item.data.get("dataset") == "traffic_sources" for item in result.mcp_results)
    matrix = next(item for item in result.diagnosis.artifacts if item.title == "一级流量来源两窗口对比")
    assert matrix.rows
    assert matrix.rows[0]["支付金额增量"] > 0
    assert matrix.rows[0]["支付金额增量"] == max(row["支付金额增量"] for row in matrix.rows)
    assert "待补采" not in result.answer
    assert any(step.name == "evidence-quality-gate" for step in result.execution_steps)


def test_channel_growth_follow_up_inherits_the_previous_analysis_end_date() -> None:
    service = AIAnalysisService()
    plan = service._agent_plan(
        AnalysisRequest(question="最近两天和前两天比较哪个渠道增长较多？", use_model=False),
        AIConversationState(
            conversation_id="agent-plan-follow-up",
            memory={"range_start": "2026-09-01", "range_end": "2026-09-07"},
        ),
        store_id=1,
    )

    assert plan is not None
    assert plan.intent.current_start == date(2026, 9, 6)
    assert plan.intent.current_end == date(2026, 9, 7)


def test_recent_sales_growth_uses_a_focused_evidence_plan() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="最近2天的销售为什么增长？",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
            page_context={"page_key": "ai"},
            use_model=False,
        ),
        store_id=1,
    )

    assert result.skill.name == "shop-overview-diagnosis"
    assert result.diagnosis.analysis_plan["name"] == "recent-sales-growth-diagnosis"
    assert result.diagnosis.coverage.covered_days == result.diagnosis.coverage.expected_days == 2
    assert "成交下降" not in result.diagnosis.headline
    assert "支付金额增长" in result.diagnosis.headline
    tools = [item.tool for item in result.mcp_results]
    assert tools.count("data.compare_periods") == 4
    assert "overview.get_store_summary" not in tools
    assert "data.catalog" not in tools
    assert any(item.data.get("dataset") == "products" for item in result.mcp_results)


def _fake_mcp(tool: str, data: dict, *, dataset: str | None = None, comparable: bool = True) -> MCPEnvelope:
    payload = dict(data)
    if dataset:
        payload["dataset"] = dataset
    return MCPEnvelope(
        request_id=f"test-{tool}",
        tool=tool,
        generated_at="2026-09-15T00:00:00+08:00",
        context=AnalysisContext(store_id=1, range_start=date(2026, 9, 8), range_end=date(2026, 9, 14)),
        status="ok" if comparable else "partial",
        data=payload,
        coverage=CoverageSummary(expected_days=7, covered_days=7 if comparable else 5, missing_dates=[] if comparable else ["2026-09-12"]),
    )


def test_promotion_question_builds_staged_agent_plan() -> None:
    plan = build_agent_plan(
        question="哪些推广计划应该降预算，哪些可以小额扩量？",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 14),
    )

    assert plan is not None
    assert plan.name == "promotion-efficiency-diagnosis"
    assert plan.primary_skill == "promotion-roi"
    assert [step.tool for step in plan.calls] == [
        "data.coverage", "promotions.get_efficiency", "data.compare_periods",
        "promotions.get_drilldown", "data.query",
    ]
    assert plan.calls[0].arguments["datasets"][-1] == "promotion_contents"
    assert plan.intent.current_start == date(2026, 9, 1)
    assert plan.intent.previous_end == date(2026, 8, 31)


def test_promotion_recent_window_does_not_use_the_whole_page_range() -> None:
    plan = build_agent_plan(
        question="最近两天推广 ROI 为什么下降？",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 14),
    )

    assert plan is not None
    assert plan.intent.current_start == date(2026, 9, 13)
    assert plan.intent.current_end == date(2026, 9, 14)
    assert plan.intent.previous_start == date(2026, 9, 11)
    assert plan.intent.previous_end == date(2026, 9, 12)


def test_promotion_diagnosis_separates_stop_loss_from_scale_test() -> None:
    plan = build_agent_plan(
        question="当前推广效率怎么样？",
        start_date=date(2026, 9, 8),
        end_date=date(2026, 9, 14),
    )
    assert plan is not None
    results = [
        _fake_mcp("data.coverage", {"datasets": []}),
        _fake_mcp("promotions.get_efficiency", {
            "summary": {"spend": 1000, "paid_amount": 1900, "roi": 1.9, "clicks": 1000, "buyers": 20},
            "campaigns": [],
        }),
        _fake_mcp("data.compare_periods", {
            "dataset": "promotion_campaigns", "comparable": True,
            "comparisons": {"spend": {"current": 1000, "previous": 900, "delta": 100, "change_percent": 11.1}},
            "current": {"rows": []}, "previous": {"rows": []},
        }, dataset="promotion_campaigns"),
        _fake_mcp("promotions.get_drilldown", {
            "level": "campaign", "total": 2, "rows": [
                {"dimension_id": "low-1", "dimension_name": "低效计划", "spend": 600, "paid_amount": 300, "roi": 0.5, "clicks": 800, "buyers": 2},
                {"dimension_id": "scale-1", "dimension_name": "高效计划", "spend": 200, "paid_amount": 800, "roi": 4, "clicks": 200, "buyers": 10},
            ],
        }),
    ]
    diagnosis = diagnose_agent_plan(plan, results)

    assert any("高花费低效率" in finding.title for finding in diagnosis.findings)
    assert any(action.priority == "P0" for action in diagnosis.actions)
    assert any(action.priority == "P2" for action in diagnosis.actions)
    assert "利润" in diagnosis.causal_boundary


def test_promotion_quality_gate_uses_observed_adgroup_before_audience_and_keyword() -> None:
    plan = build_agent_plan(
        question="分析低效推广计划",
        start_date=date(2026, 9, 8),
        end_date=date(2026, 9, 14),
    )
    assert plan is not None
    campaign = _fake_mcp("promotions.get_drilldown", {
        "level": "campaign", "total": 1,
        "rows": [{"dimension_id": "campaign-1", "spend": 500, "paid_amount": 200, "roi": 0.4}],
    })

    first_round = _promotion_drilldown_repairs(plan, [campaign])
    assert [item.arguments["level"] for item in first_round] == ["adgroup", "product"]
    assert all(item.arguments["campaign_id"] == "campaign-1" for item in first_round)

    adgroup = _fake_mcp("promotions.get_drilldown", {
        "level": "adgroup", "total": 1,
        "rows": [{"dimension_id": "adgroup-9", "spend": 400, "paid_amount": 100, "roi": 0.25}],
    })
    second_round = _promotion_drilldown_repairs(plan, [campaign, adgroup])
    assert [item.arguments["level"] for item in second_round] == ["audience", "keyword"]
    assert all(item.arguments["adgroup_id"] == "adgroup-9" for item in second_round)
